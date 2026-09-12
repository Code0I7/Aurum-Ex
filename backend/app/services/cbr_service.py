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

from app.models.currency import ExchangeRate
from app.services.currency_service import (
    currencies_in_use,
    get_base_currency,
    watched_currencies,
)

CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"

# Валюта, к которой котирует источник. У ЦБ это рубль, и в самом ответе его
# нет: остальные валюты выражены в нём.
#
# Отдельная константа, а не «RUB» по тексту: базовая валюта установки и
# опорная валюта источника — разные вещи, и совпадают они только у
# рублёвой установки. Пока их писали одним словом, второй источник было
# некуда приткнуть, а доллар в базе молча получал рублёвые котировки.
REFERENCE_CURRENCY = "RUB"

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


def to_base_rates(quotes: dict[str, Decimal], base_currency: str) -> dict[str, Decimal]:
    """Котировки источника, пересчитанные к базовой валюте установки.

    Источник котирует всё к своей опорной валюте. Пока база рублёвая, это
    одно и то же, и приложение годами считало, что так будет всегда: взять
    число из ответа ЦБ и положить его как «столько базовых единиц за
    единицу». Поставь базовой валютой доллар — и рублёвые котировки легли бы
    в таблицу под видом долларовых, молча и без единого признака ошибки.

    Пересчёт — деление: если рубль даёт 81,2 за доллар и 95,0 за евро, то
    евро стоит 95,0 ÷ 81,2 = 1,17 доллара. Отдельный источник ради другой
    базы не нужен — достаточно, чтобы он котировал обе валюты.

    Опорная валюта источника в ответе не приходит (она и есть единица), но
    установке с другой базой нужна: доллар, держащий рубли, должен знать их
    курс. Поэтому она добавляется обратным числом.
    """
    base = base_currency.upper()
    if base == REFERENCE_CURRENCY:
        return quotes

    reference_per_base = quotes.get(base)
    if reference_per_base is None or reference_per_base <= 0:
        # Источник не котирует базовую валюту — считать не из чего. Молча
        # положить единицу здесь значит испортить каждую сумму установки.
        raise CbrUnavailable(f"источник не котирует базовую валюту {base}")

    converted = {
        code: value / reference_per_base for code, value in quotes.items() if code != base
    }
    converted[REFERENCE_CURRENCY] = Decimal("1") / reference_per_base
    return converted


async def sync_rates_for_date(session: AsyncSession, on_date: date_) -> int:
    """Загружает курсы на дату и сохраняет те, что относятся к валютам,
    которыми пользователь действительно пользуется.

    Возвращает число сохранённых курсов. Хранить полторы сотни котировок на
    каждый день ради двух используемых — ровно та ошибка, из-за которой
    самодельные таблицы с курсами становятся неповоротливыми.

    Набор берётся из самих записей, а не только из справочника валют:
    валюта, забытая в справочнике, означала бы молча не загруженный курс.
    Доллар, посчитанный по единице, выглядит как обычное число, и заметен он
    только по итогам года.

    К ним добавляются те, за курсом которых человек просто следит: у
    рублёвой установки это доллар, евро и юань, и своих счетов в них может
    не быть вовсе. Расчётам они не нужны, но блок «Курсы» без них пуст.
    """
    known = await currencies_in_use(session) | await watched_currencies(session)
    if not known:
        return 0

    quotes, published_for = await fetch_rates(on_date)
    rates = to_base_rates(quotes, await get_base_currency(session))

    existing = {
        row.code: row
        for row in (
            await session.execute(
                select(ExchangeRate).where(
                    ExchangeRate.rate_date == on_date, ExchangeRate.code.in_(known)
                )
            )
        )
        .scalars()
        .all()
    }

    saved = 0
    for code in known:
        rate = rates.get(code)
        if rate is None:
            continue
        stored = existing.get(code)
        if stored is None:
            session.add(
                ExchangeRate(code=code, rate_date=on_date, rate=rate, published_for=published_for)
            )
            saved += 1
            continue
        # Записанный курс переписывается ровно в одном случае: когда в
        # прошлый раз сюда лёг курс предыдущего рабочего дня — ЦБ на эту
        # дату ещё не опубликовал, источник отдал последний известный, — а
        # теперь публикация появилась. Это не «переписать прошлое», а
        # заменить временную подстановку настоящим значением.
        #
        # Всё остальное заморожено навсегда. Дата публикации неизвестна
        # (старые записи) — значит, сравнивать не с чем, и запись не
        # трогается: лучше оставить как есть, чем переписать наугад.
        if stored.published_for is not None and published_for > stored.published_for:
            stored.rate = rate
            stored.published_for = published_for
            saved += 1

    if saved:
        await session.commit()
    return saved
