"""Загрузка курсов валют с сайта Центробанка России.

Источник — официальный адрес с историей на любую дату:

    https://www.cbr.ru/scripts/XML_daily.asp?date_req=ДД.ММ.ГГГГ

Он отдаёт XML, работает с 1992 года, не требует ключа и регистрации. Разбор
HTML-страницы сайта не рассматривался: вёрстку меняют, и такой разбор
однажды молча ломается, а этот адрес стабилен годами.

Три особенности источника, каждая из которых иначе портит расчёты:

  * **котировка идёт за лот.** Доллар публикуется за 1 единицу, а иена или
    вона — за 100 и за 1000. Без деления на номинал курс завышается в сотню
    раз, причём тихо;
  * **по выходным и праздникам курса нет.** ЦБ публикует котировки только
    по рабочим дням, и запрос на воскресенье вернёт данные пятницы. Это
    ожидаемое поведение, а не ошибка: в такие дни и действует пятничный
    курс;
  * **числа записаны с запятой** как десятичным разделителем.

Базовая валюта здесь не участвует вовсе: её курс к самой себе всегда ровно
1 и в базе не хранится (см. services/currency_service.py).
"""
from datetime import date as date_
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.currency import Currency, ExchangeRate

CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"

# ЦБ отдаёт XML в кодировке windows-1251 и объявляет её в заголовке
# документа. httpx угадывает кодировку по HTTP-заголовку, где её нет,
# поэтому декодируем сами.
CBR_ENCODING = "windows-1251"

REQUEST_TIMEOUT = 15.0


class CbrUnavailable(RuntimeError):
    """Сайт ЦБ не ответил или ответил неразборчиво.

    Отдельный тип нужен, чтобы вызывающий код мог отличить «курсов сегодня
    нет» от «что-то сломалось в самом приложении»: первое — обычное дело,
    второе требует внимания."""


def _parse_decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw.strip().replace(",", "."))
    except InvalidOperation:
        return None


def parse_cbr_xml(payload: str) -> dict[str, Decimal]:
    """Разбирает ответ ЦБ в словарь «код валюты → курс за одну единицу».

    Деление на номинал делается здесь, а не при использовании: забыть его
    в одном из мест — значит получить курс, завышенный в сто раз, и заметить
    это далеко не сразу.
    """
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        raise CbrUnavailable(f"Не удалось разобрать ответ ЦБ: {error}") from error

    rates: dict[str, Decimal] = {}
    for node in root.findall("Valute"):
        code = (node.findtext("CharCode") or "").strip().upper()
        value = _parse_decimal(node.findtext("Value"))
        nominal = _parse_decimal(node.findtext("Nominal")) or Decimal("1")
        if not code or value is None or nominal == 0:
            continue
        rates[code] = value / nominal
    return rates


async def fetch_rates(on_date: date_) -> tuple[dict[str, Decimal], date_]:
    """Курсы на дату и дата, на которую они реально опубликованы.

    Вторая величина важна: запрос на выходной вернёт котировки последнего
    рабочего дня, и об этом лучше знать, чем гадать, почему в субботу и
    воскресенье курс одинаковый.
    """
    params = {"date_req": on_date.strftime("%d.%m.%Y")}
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(CBR_URL, params=params)
            response.raise_for_status()
            payload = response.content.decode(CBR_ENCODING, errors="replace")
    except httpx.HTTPError as error:
        raise CbrUnavailable(f"Сайт ЦБ недоступен: {error}") from error

    rates = parse_cbr_xml(payload)

    # Дата публикации лежит в атрибуте корневого узла.
    published_for = on_date
    try:
        root = ElementTree.fromstring(payload)
        raw_date = root.attrib.get("Date")
        if raw_date:
            day, month, year = (int(part) for part in raw_date.split("."))
            published_for = date_(year, month, day)
    except (ElementTree.ParseError, ValueError):
        # Атрибут не разобрался — не повод терять сами курсы.
        pass

    return rates, published_for


async def sync_rates_for_date(session: AsyncSession, on_date: date_, base_currency: str) -> int:
    """Загружает курсы на дату и сохраняет те, что относятся к валютам,
    которыми пользователь действительно пользуется.

    Возвращает число сохранённых курсов. Валюты, которых нет в справочнике,
    пропускаются: хранить полторы сотни котировок на каждый день ради двух
    используемых — ровно та ошибка, из-за которой самодельные таблицы с
    курсами становятся неповоротливыми.
    """
    known = {
        code
        for (code,) in (await session.execute(select(Currency.code).where(Currency.is_active.is_(True)))).all()
        if code.upper() != base_currency.upper()
    }
    if not known:
        return 0

    rates, published_for = await fetch_rates(on_date)

    existing = {
        code
        for (code,) in (
            await session.execute(
                select(ExchangeRate.code).where(
                    ExchangeRate.rate_date == on_date, ExchangeRate.code.in_(known)
                )
            )
        ).all()
    }

    saved = 0
    for code in known:
        rate = rates.get(code)
        if rate is None or code in existing:
            continue
        session.add(ExchangeRate(code=code, rate_date=on_date, rate=rate, published_for=published_for))
        saved += 1

    if saved:
        await session.commit()
    return saved
