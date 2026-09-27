"""Загрузка курсов валют с сайта Центробанка России.

Источник — официальный адрес с историей на любую дату:

    https://www.cbr.ru/scripts/XML_daily.asp?date_req=ДД.ММ.ГГГГ

И второй, отдающий одну валюту сразу за диапазон дат:

    https://www.cbr.ru/scripts/XML_dynamic.asp?date_req1=&date_req2=&VAL_NM_RQ=

Он нужен истории. Через первый адрес год курсов — это двести пятьдесят
обращений, по одному на день; через второй — одно на валюту. Цена в том, что
валюту он опознаёт не по буквенному коду, а по своему внутреннему («R01235» у
доллара), и этот код приходится сначала узнать из ответа первого адреса.

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
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.currency import Currency, ExchangeRate
from app.services.currency_service import (
    currencies_in_use,
    get_base_currency,
    watched_currencies,
)

CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
# История одной валюты за диапазон дат — одним обращением.
CBR_DYNAMIC_URL = "https://www.cbr.ru/scripts/XML_dynamic.asp"

# Сколько последних дней догружать при обычном обновлении курсов.
#
# Динамика в блоке «Курсы» считается к предыдущему известному курсу, а в базе
# лежат только те дни, за которыми ходили. Пока ходили по одному дню, между
# двумя нажатиями оказывалась неделя, и «изменение» было недельным при
# дневной подписи. Неделя закрывает и выходные, и праздники подряд.
RECENT_HISTORY_DAYS = 7

# Как часто можно повторно спрашивать источник об одном и том же диапазоне.
#
# Праздников источник не публикует вовсе, поэтому «в диапазоне не хватает
# рабочего дня» остаётся правдой навсегда, и по одному этому признаку каждое
# открытие графика било бы в сайт ЦБ. Память о том, что уже спрашивали,
# живёт в процессе: после перезапуска спросим ещё раз — это дешевле, чем
# держать для такого таблицу.
HISTORY_ASK_INTERVAL = timedelta(hours=6)
_HISTORY_ASKED: dict[tuple[str, date_, date_], datetime] = {}

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


def parse_cbr_codes(payload: str) -> dict[str, str]:
    """Внутренние коды валют источника: «USD» → «R01235».

    Приходят в том же ответе, что и котировки, и нужны второму адресу — тому,
    что отдаёт историю за диапазон. Отдельная функция, а не поле в разборе
    курсов: курсы читают в десяти местах, а коды — только при загрузке.
    """
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        raise CbrUnavailable(f"Не удалось разобрать ответ ЦБ: {error}") from error

    codes: dict[str, str] = {}
    for node in root.findall("Valute"):
        code = (node.findtext("CharCode") or "").strip().upper()
        internal = (node.attrib.get("ID") or "").strip()
        if code and internal:
            codes[code] = internal
    return codes


def parse_cbr_history(payload: str) -> dict[date_, Decimal]:
    """Разбирает историю одной валюты: «дата → курс за одну единицу».

    Номинал приходит в каждой записи и может меняться от года к году —
    делим на тот, что стоит в самой записи, а не на сегодняшний.
    """
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        raise CbrUnavailable(f"Не удалось разобрать ответ ЦБ: {error}") from error

    rates: dict[date_, Decimal] = {}
    for node in root.findall("Record"):
        raw_date = (node.attrib.get("Date") or "").strip()
        value = _parse_decimal(node.findtext("Value"))
        nominal = _parse_decimal(node.findtext("Nominal")) or Decimal("1")
        if not raw_date or value is None or nominal == 0:
            continue
        try:
            day, month, year = (int(part) for part in raw_date.split("."))
            rates[date_(year, month, day)] = value / nominal
        except ValueError:
            # Одна неразобранная строка не повод терять остальные.
            continue
    return rates


async def _get(url: str, params: dict[str, str]) -> str:
    """Ответ источника текстом. Кодировку объявляет сам документ, а в
    HTTP-заголовке её нет, поэтому декодируем сами."""
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.content.decode(CBR_ENCODING, errors="replace")
    except httpx.HTTPError as error:
        raise CbrUnavailable(f"Сайт ЦБ недоступен: {error}") from error


async def fetch_daily(on_date: date_) -> tuple[dict[str, Decimal], dict[str, str], date_]:
    """Курсы на дату, внутренние коды валют и дата публикации — одним
    обращением: всё это лежит в одном и том же ответе."""
    payload = await _get(CBR_URL, {"date_req": on_date.strftime("%d.%m.%Y")})
    rates = parse_cbr_xml(payload)
    codes = parse_cbr_codes(payload)

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

    return rates, codes, published_for


async def fetch_rates(on_date: date_) -> tuple[dict[str, Decimal], date_]:
    """Курсы на дату и дата, на которую они реально опубликованы.

    Вторая величина важна: запрос на выходной вернёт котировки последнего
    рабочего дня, и об этом лучше знать, чем гадать, почему в субботу и
    воскресенье курс одинаковый.

    Обёртка над fetch_daily: внутренние коды валют здесь никому не нужны, а
    звать функцию с тремя значениями там, где важны два, — приглашение
    однажды перепутать их местами.
    """
    rates, _codes, published_for = await fetch_daily(on_date)
    return rates, published_for


async def fetch_history(cbr_code: str, start: date_, end: date_) -> dict[date_, Decimal]:
    """История одной валюты за диапазон — одним обращением.

    Источник отдаёт только те дни, когда публиковал: выходных и праздников в
    ответе нет вовсе. Достраивать их здесь нечем и не нужно — в такие дни
    действует курс последнего рабочего дня, и так его и читает всё
    приложение (см. currency_service.get_rate).
    """
    payload = await _get(
        CBR_DYNAMIC_URL,
        {
            "date_req1": start.strftime("%d/%m/%Y"),
            "date_req2": end.strftime("%d/%m/%Y"),
            "VAL_NM_RQ": cbr_code,
        },
    )
    return parse_cbr_history(payload)


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

    quotes, cbr_codes, published_for = await fetch_daily(on_date)
    rates = to_base_rates(quotes, await get_base_currency(session))
    # Внутренние коды валют запоминаются заодно: другого повода за ними
    # ходить нет, а истории они нужны.
    await _remember_cbr_codes(session, cbr_codes)

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


async def _remember_cbr_codes(session: AsyncSession, cbr_codes: dict[str, str]) -> None:
    """Записывает внутренние коды валют источника тем валютам, у которых их
    ещё нет. Уже записанные не трогаются: код валюты у источника не меняется,
    а лишняя запись в базу на каждое обновление курсов ни к чему."""
    rows = (
        (await session.execute(select(Currency).where(Currency.cbr_code.is_(None))))
        .scalars()
        .all()
    )
    changed = False
    for row in rows:
        internal = cbr_codes.get(row.code.upper())
        if internal:
            row.cbr_code = internal
            changed = True
    if changed:
        await session.commit()


async def _ensure_cbr_code(session: AsyncSession, code: str) -> str | None:
    """Внутренний код валюты у источника, при необходимости узнав его.

    Пустой он ровно до первой загрузки курсов, а история нужна бывает раньше:
    человек открывает график, ещё ничего не обновив. Тогда один дневной
    запрос заполняет коды всем валютам сразу.
    """
    currency = await session.get(Currency, code.upper())
    if currency is not None and currency.cbr_code:
        return currency.cbr_code

    _quotes, cbr_codes, _published = await fetch_daily(date_.today())
    await _remember_cbr_codes(session, cbr_codes)
    return cbr_codes.get(code.upper())


def _days(start: date_, end: date_):
    """Все календарные дни диапазона, включая концы."""
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


async def sync_history(session: AsyncSession, code: str, start: date_, end: date_) -> int:
    """Догружает историю курса одной валюты за диапазон дат.

    Возвращает число сохранённых курсов. Уже сохранённые дни не трогаются:
    курс прошедшего дня не меняется никогда. Единственное исключение — то же,
    что и у дневной загрузки: если на эту дату лежал курс предыдущего рабочего
    дня как подстановка, а теперь пришла настоящая публикация, она её
    заменяет.

    Базовая валюта установки пропускается: её курс к самой себе всегда 1 и в
    таблице не хранится. Опорная валюта источника истории не имеет — источник
    котирует всё к ней, — поэтому её курс получается обратным курсом базовой
    валюты к ней.
    """
    code = code.upper()
    base = (await get_base_currency(session)).upper()
    if code == base or end < start:
        return 0

    base_quotes: dict[date_, Decimal] = {}
    if base != REFERENCE_CURRENCY:
        base_cbr = await _ensure_cbr_code(session, base)
        if base_cbr is None:
            raise CbrUnavailable(f"источник не котирует базовую валюту {base}")
        base_quotes = await fetch_history(base_cbr, start, end)

    if code == REFERENCE_CURRENCY:
        rates = {day: Decimal("1") / quote for day, quote in base_quotes.items() if quote > 0}
    else:
        cbr_code = await _ensure_cbr_code(session, code)
        if cbr_code is None:
            raise CbrUnavailable(f"источник не знает валюту {code}")
        quotes = await fetch_history(cbr_code, start, end)
        if base == REFERENCE_CURRENCY:
            rates = quotes
        else:
            # Обе котировки к опорной валюте: евро в долларах — это евро в
            # рублях, делённое на доллар в рублях, и только за тот же день.
            rates = {
                day: quote / base_quotes[day]
                for day, quote in quotes.items()
                if base_quotes.get(day, Decimal("0")) > 0
            }

    existing = {
        row.rate_date: row
        for row in (
            await session.execute(
                select(ExchangeRate).where(
                    ExchangeRate.code == code,
                    ExchangeRate.rate_date >= start,
                    ExchangeRate.rate_date <= end,
                )
            )
        )
        .scalars()
        .all()
    }

    saved = 0
    for day, rate in sorted(rates.items()):
        stored = existing.get(day)
        if stored is None:
            # Дата публикации здесь равна самой дате: источник отдаёт только
            # те дни, когда публиковал.
            session.add(ExchangeRate(code=code, rate_date=day, rate=rate, published_for=day))
            saved += 1
        elif stored.published_for is not None and day > stored.published_for:
            stored.rate = rate
            stored.published_for = day
            saved += 1
    if saved:
        await session.commit()
    return saved


async def sync_history_if_needed(session: AsyncSession, code: str, start: date_, end: date_) -> int:
    """Догружает историю, только если есть что догружать.

    Два условия, и оба нужны. В диапазоне не хватает хотя бы одного рабочего
    дня — иначе ходить незачем. И за этим же диапазоном не спрашивали в
    последние часы: праздников источник не публикует вовсе, поэтому первое
    условие остаётся правдой навсегда, и по нему одному каждое открытие
    графика било бы в сайт ЦБ.
    """
    code = code.upper()
    today = date_.today()
    stored = {
        row
        for (row,) in (
            await session.execute(
                select(ExchangeRate.rate_date).where(
                    ExchangeRate.code == code,
                    ExchangeRate.rate_date >= start,
                    ExchangeRate.rate_date <= end,
                )
            )
        ).all()
    }
    missing = any(day.weekday() < 5 and day not in stored for day in _days(start, min(end, today)))
    if not missing:
        return 0

    key = (code, start, end)
    asked = _HISTORY_ASKED.get(key)
    now = datetime.now(timezone.utc)
    if asked is not None and now - asked < HISTORY_ASK_INTERVAL:
        return 0
    _HISTORY_ASKED[key] = now
    return await sync_history(session, code, start, end)


async def sync_recent_history(session: AsyncSession) -> int:
    """Догружает последнюю неделю по всем валютам, которые показываются.

    Зовётся обычным обновлением курсов. Без этого динамика считалась не за
    день: в базе лежали только те дни, за которыми ходили, и между двумя
    нажатиями оказывалась неделя — «изменение» было недельным при дневной
    подписи.
    """
    base = (await get_base_currency(session)).upper()
    codes = sorted((await currencies_in_use(session) | await watched_currencies(session)) - {base})
    today = date_.today()
    saved = 0
    for code in codes:
        try:
            saved += await sync_history(
                session, code, today - timedelta(days=RECENT_HISTORY_DAYS), today
            )
        except CbrUnavailable:
            # Сайт лёг посреди обхода: сохранённое остаётся, остальное
            # доберётся следующим нажатием.
            break
    return saved
