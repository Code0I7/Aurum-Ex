"""Перенос истории из табличного учёта.

Читает два CSV, выгруженных из Google Sheets: лист настроек (счета,
категории, персоны, единицы, магазины) и лист транзакций. Всё остальное в
той книге — производные расчёты, которые Aurum-Ex считает сам.

Разбор устроен вокруг четырёх особенностей исходных данных, и каждая
требует не перекладывания, а перевода смысла:

  * **вид ДДС не совпадает с типом операции.** «Доходы» и «Расходы»
    переносятся напрямую, а «Зачисление» и «Списание» — это две половины
    одного перевода, которые надо склеить обратно в одну запись. В данных
    склеивать их надо по дате и сумме — других связей в листе нет;
  * **«Присвоить» и «Изъять» — не корректировки, а конверты.** Операции
    фиктивного счёта, на котором деньги откладывались на цель и потом
    тратились; становятся движениями по целям;
  * **«Стартовое внесение» — не доход.** Деньги, лежавшие на счёте до
    начала учёта. Проведённые доходом, они завышают заработок за первый
    год; переносятся в начальный остаток счёта;
  * **обнулённое количество — это «не учитывать».** Возвращённый товар или
    отменённый заказ: покупка была, помнить о ней нужно, а в суммы она
    входить не должна.

Импорт идёт одной транзакцией базы: либо переносится всё, либо не
переносится ничего. Половина истории хуже, чем её отсутствие, — по ней
нельзя понять, чего не хватает.
"""
import csv
import io
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import date as date_
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.enums import (
    AccountKind,
    AccountNature,
    CategoryKind,
    GoalStatus,
    ParticipantKind,
    TransactionType,
)
from app.models.goal import Goal, GoalContribution
from app.models.participant import Participant
from app.models.store import Store
from app.models.work_period import WorkPeriod
from app.models.transaction import Transaction
from app.services.category_grouping import build_nesting

# Виды ДДС из исходной таблицы. Строки на русском — это буквально то, что
# лежит в колонке; сопоставление вынесено сюда, чтобы не разбредаться
# сравнениями со строковыми литералами по всему разбору.
DDS_INCOME = "Доходы"
DDS_EXPENSE = "Расходы"
DDS_TRANSFER_IN = "Зачисление"
DDS_TRANSFER_OUT = "Списание"
DDS_RESERVE = "Присвоить"
DDS_RELEASE = "Изъять"

# Комментарий стартового взноса. Ищется по вхождению, а не по равенству:
# в данных он записан как «Стартовое внесение», но опечатка или уточнение
# в скобках не должны превратить остаток обратно в доход.
OPENING_MARKER = "стартов"


@dataclass
class SheetSettings:
    """Разобранный лист настроек: то, что таблица знает о счетах, единицах и
    людях, но не повторяет в каждой операции.

    Лист необязателен — импорт работает и без него, просто счета получают
    вид по догадке из названия, а валюта у всех одна. С листом догадок
    меньше: там прямо сказано, какой счёт в какой валюте."""

    # Название счёта -> буквенный код валюты.
    account_currencies: dict[str, str] = field(default_factory=dict)
    # Порядок названий счетов, как они идут в таблице.
    accounts: list[str] = field(default_factory=list)
    units: list[str] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)
    pets: list[str] = field(default_factory=list)
    stores: list[str] = field(default_factory=list)
    base_currency: str | None = None
    # Год -> отработанные часы. В таблице они годовые, а нужны помесячные,
    # поэтому переносятся как есть и раскладываются по месяцам отдельно.
    work_hours_by_year: dict[int, Decimal] = field(default_factory=dict)
    workdays_by_year: dict[int, int] = field(default_factory=dict)


@dataclass
class ImportResult:
    """Что фактически перенеслось. Возвращается наружу и показывается
    человеку: импорт без отчёта — это импорт, которому нельзя доверять."""

    accounts: int = 0
    categories: int = 0
    participants: int = 0
    goals: int = 0
    transactions: int = 0
    transfers: int = 0
    goal_contributions: int = 0
    work_periods: int = 0
    stores: int = 0
    issues: list["ImportIssue"] = field(default_factory=list)


@dataclass
class ImportIssue:
    """Строка, которую не удалось перенести как есть."""

    row: int
    reason: str
    detail: str = ""


@dataclass
class ParsedTransaction:
    row: int
    date: date_
    description: str
    amount: Decimal
    account: str
    dds: str
    category: str | None
    subcategory: str | None
    participant: str | None
    unit: str | None
    goal: str | None
    quantity: Decimal | None
    is_excluded: bool
    # Заполняется при роспуске копилки: счёт, ставший второй стороной
    # перевода вместо неё.
    envelope_target: str | None = None


@dataclass
class ImportPlan:
    """Что получится, если применить импорт. Собирается целиком до записи в
    базу, чтобы отчёт можно было показать до, а не после."""

    accounts: dict[str, Decimal] = field(default_factory=dict)
    categories: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    participants: set[str] = field(default_factory=set)
    units: set[str] = field(default_factory=set)
    goals: set[str] = field(default_factory=set)
    # Счета-копилки, распущенные в цели: «имя копилки → счёт-источник».
    envelopes: dict[str, str | None] = field(default_factory=dict)
    # Счета, опознанные как кредитные по начисленным на них процентам.
    credit_accounts: set[str] = field(default_factory=set)

    incomes: list[ParsedTransaction] = field(default_factory=list)
    expenses: list[ParsedTransaction] = field(default_factory=list)
    transfers: list[tuple[ParsedTransaction, ParsedTransaction]] = field(default_factory=list)
    reserves: list[ParsedTransaction] = field(default_factory=list)
    releases: list[ParsedTransaction] = field(default_factory=list)
    openings: list[ParsedTransaction] = field(default_factory=list)

    issues: list[ImportIssue] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return (
            len(self.incomes)
            + len(self.expenses)
            + len(self.transfers) * 2
            + len(self.reserves)
            + len(self.releases)
            + len(self.openings)
        )


def parse_amount(raw: str | None) -> Decimal | None:
    """Число из русской таблицы: пробелы-разделители тысяч (включая
    неразрывный), запятая как десятичный знак, символ валюты в хвосте.

    Прочерк вместо суммы — это не ошибка разбора, а обнулённая запись:
    человек оставлял её как памятку, обнулив количество. Возвращается None,
    и вызывающий код помечает строку как «не учитывать».
    """
    if raw is None:
        return None
    cleaned = raw.replace("\xa0", "").replace(" ", "").replace("₽", "").replace(",", ".").strip()
    if cleaned in {"", "-", "—", "–"}:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_date(raw: str | None) -> date_ | None:
    """Дата в формате ДД.ММ.ГГГГ, как её отдаёт Google Sheets по-русски."""
    if not raw:
        return None
    match = re.match(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*$", raw)
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return date_(year, month, day)
    except ValueError:
        return None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.replace("\xa0", " ").strip()
    return text or None


# Подписи строк листа настроек. Сравнение идёт по началу строки без учёта
# регистра: в таблице встречаются лишние пробелы и разный регистр, а
# смысловая часть подписи стабильна.
_SETTINGS_ROWS = {
    "знак валют": "currency_symbols",
    "буквенный код валют": "currency_codes",
    "карта / счет": "accounts",
    "присвоить валюту карте": "account_currencies",
    "единица измерения": "units",
    "основная валюта": "base_currency",
    "персона": "participants",
    "животные": "pets",
    "локация / магазин": "stores",
    "рабочих часов в году": "work_hours",
    "рабочих дней в году": "workdays",
    "год": "years",
}


def _settings_row_key(label: str | None) -> str | None:
    if not label:
        return None
    lowered = label.strip().lower()
    for prefix, key in _SETTINGS_ROWS.items():
        if lowered.startswith(prefix):
            return key
    return None


def parse_settings_csv(content: str) -> SheetSettings:
    """Разбирает лист настроек.

    Таблица устроена «строка — это список»: подпись в первом столбце, дальше
    значения. Порядок строк не фиксирован, поэтому опознаём их по подписи, а
    не по номеру: в чужой копии книги строки легко оказываются сдвинутыми.
    """
    settings = SheetSettings()
    rows: dict[str, list[str]] = {}
    years: list[int] = []

    for raw in csv.reader(io.StringIO(content)):
        if not raw:
            continue
        # Подпись может стоять в первом или во втором столбце — в разных
        # копиях книги первый столбец бывает пустым. Значения идут строго
        # ПОСЛЕ подписи: если начать читать с фиксированной колонки, сама
        # подпись попадёт в список значений и сдвинет всё на единицу — на
        # строке с годовыми часами это тихо перевешивает часы на соседний
        # год.
        label_index = 0 if _settings_row_key(_clean(raw[0])) else 1 if len(raw) > 1 else None
        if label_index is None:
            continue
        key = _settings_row_key(_clean(raw[label_index]))
        if key is None:
            continue
        values = [_clean(cell) for cell in raw[label_index + 1 :]]
        rows[key] = [value for value in values if value]

    # Знаки валют и их коды идут двумя параллельными строками — по ним
    # восстанавливается, что «₽» это RUB.
    symbols = rows.get("currency_symbols", [])
    codes = rows.get("currency_codes", [])
    symbol_to_code = {symbol: code.upper() for symbol, code in zip(symbols, codes) if symbol and code}

    settings.accounts = rows.get("accounts", [])
    account_symbols = rows.get("account_currencies", [])
    for index, name in enumerate(settings.accounts):
        symbol = account_symbols[index] if index < len(account_symbols) else None
        code = symbol_to_code.get(symbol or "")
        if code:
            settings.account_currencies[name] = code

    settings.units = rows.get("units", [])
    settings.stores = rows.get("stores", [])

    # В строке «Персона» первое значение — счётчик, а не имя.
    settings.participants = [value for value in rows.get("participants", []) if not value.isdigit()]
    settings.pets = [value for value in rows.get("pets", []) if not value.isdigit()]

    base = rows.get("base_currency", [])
    for value in base:
        code = symbol_to_code.get(value)
        if code:
            settings.base_currency = code
            break

    # Годовые часы и дни: строка «Год» задаёт колонки, остальные значения
    # выстраиваются под ними.
    for value in rows.get("years", []):
        if value.isdigit():
            years.append(int(value))
    for key, target in (("work_hours", settings.work_hours_by_year), ("workdays", settings.workdays_by_year)):
        for index, value in enumerate(rows.get(key, [])):
            if index >= len(years):
                break
            number = parse_amount(value)
            if number is not None:
                target[years[index]] = number if key == "work_hours" else int(number)

    return settings


def parse_transactions_csv(content: str) -> tuple[list[ParsedTransaction], list[ImportIssue]]:
    """Разбирает лист «Транзакции» в список записей и список проблем."""
    reader = csv.DictReader(io.StringIO(content))
    parsed: list[ParsedTransaction] = []
    issues: list[ImportIssue] = []

    for index, raw in enumerate(reader, start=2):  # строка 1 — заголовок
        tx_date = parse_date(raw.get("Дата"))
        if tx_date is None:
            # Пустые строки в конце листа — не ошибка, их просто нет.
            if not any((value or "").strip() for value in raw.values()):
                continue
            issues.append(ImportIssue(row=index, reason="no_date", detail=raw.get("Дата") or ""))
            continue

        dds = _clean(raw.get("ДДС")) or ""
        amount = parse_amount(raw.get("Сумма"))
        quantity = parse_amount(raw.get("Кол-во"))

        # Обнулённая запись: сумма прочерком или количество в ноль. Это
        # самодельное «не учитывать» из исходной таблицы — покупка была, но
        # в деньгах её быть не должно.
        excluded = amount is None or (quantity is not None and quantity == 0)
        if amount is None:
            # Цена сохранилась, даже когда сумма обнулена, — она и
            # восстанавливает, о какой покупке шла речь.
            amount = parse_amount(raw.get("Цена")) or Decimal("0")

        account = _clean(raw.get("Карта / Счет"))
        if not account:
            issues.append(ImportIssue(row=index, reason="no_account"))
            continue

        parsed.append(
            ParsedTransaction(
                row=index,
                date=tx_date,
                # Пусто остаётся пустым. Заглушка «Без описания» стояла
                # здесь, пока описание было обязательным полем: у половины
                # строк исходной таблицы комментария нет, и импорт иначе не
                # проходил. Поле стало необязательным в beta.4, а заглушка
                # осталась — и превратилась в 243 строки текста, который
                # ничего не сообщает, зато мешает: он попадает в поиск, в
                # проверку повторов и просто занимает место в списке.
                description=_clean(raw.get("Комментарий статьи Расходов или Доходов")),
                amount=amount,
                account=account,
                dds=dds,
                category=_clean(raw.get("Категория ДДС")),
                subcategory=_clean(raw.get("Подкатегории ДДС")),
                participant=_clean(raw.get("Персона")),
                unit=_clean(raw.get("Ед.изм-ия")),
                goal=_clean(raw.get("Цель")),
                quantity=quantity,
                is_excluded=excluded,
            )
        )

    return parsed, issues


def match_transfers(
    rows: list[ParsedTransaction],
) -> tuple[list[tuple[ParsedTransaction, ParsedTransaction]], list[ImportIssue]]:
    """Склеивает «Списание» и «Зачисление» обратно в переводы.

    Пара ищется по дате и сумме — других связей в таблице нет. Когда в один
    день два перевода на одинаковую сумму, какое списание какому зачислению
    соответствует, данные не говорят; берётся первое подходящее, и это
    честный компромисс: суммы и балансы сойдутся в любом случае, различаться
    может только направление между двумя счетами.

    Несклеенные половины не выбрасываются, а попадают в отчёт: потерять
    перевод молча — худшее, что может сделать импорт.
    """
    outgoing = [row for row in rows if row.dds == DDS_TRANSFER_OUT]
    incoming = [row for row in rows if row.dds == DDS_TRANSFER_IN]

    # Индексируем приходы по ключу «дата + сумма», сохраняя порядок.
    index: dict[tuple[date_, Decimal], list[ParsedTransaction]] = defaultdict(list)
    for row in incoming:
        index[(row.date, row.amount)].append(row)

    pairs: list[tuple[ParsedTransaction, ParsedTransaction]] = []
    issues: list[ImportIssue] = []
    used: set[int] = set()

    for row in outgoing:
        candidates = index.get((row.date, row.amount), [])
        match = next((candidate for candidate in candidates if id(candidate) not in used), None)
        if match is None:
            issues.append(
                ImportIssue(row=row.row, reason="unmatched_transfer_out", detail=f"{row.date} {row.amount}")
            )
            continue
        used.add(id(match))
        pairs.append((row, match))

    for row in incoming:
        if id(row) not in used:
            issues.append(
                ImportIssue(row=row.row, reason="unmatched_transfer_in", detail=f"{row.date} {row.amount}")
            )

    return pairs, issues


def detect_envelope_accounts(rows: list[ParsedTransaction]) -> dict[str, str | None]:
    """Находит счета-копилки и счёт, с которого на них клали деньги.

    Копилка — приём, к которому приходят почти все, кто ведёт учёт в
    таблице: заводится фиктивный счёт, на него «переводятся» отложенные
    деньги, и по нему видно, сколько накоплено. Физически деньги никуда не
    уходят и продолжают лежать на карте.

    В Aurum-Ex для этого есть цели с резервом внутри счёта, поэтому копилку
    надо не переносить, а распустить: взносы станут движениями по целям, а
    технические переводы на неё и обратно — исчезнут. Оставить их значило бы
    показать перемещение денег, которого не было.

    Признак копилки: на счёте есть операции откладывания, и НЕТ ни одного
    настоящего дохода или расхода — только они и парные переводы.

    Возвращает «имя копилки → имя счёта, откуда шли деньги». Второе нужно,
    чтобы привязать цели к настоящему счёту; если однозначно определить не
    вышло, там None.
    """
    by_account: dict[str, list[ParsedTransaction]] = defaultdict(list)
    for row in rows:
        by_account[row.account].append(row)

    envelopes: dict[str, str | None] = {}
    for name, account_rows in by_account.items():
        kinds = {row.dds for row in account_rows}
        has_reserves = bool(kinds & {DDS_RESERVE, DDS_RELEASE})
        has_real_money = bool(kinds & {DDS_INCOME, DDS_EXPENSE})
        if not has_reserves or has_real_money:
            continue

        # Счёт-источник: тот, с которого чаще всего списывали в пользу этой
        # копилки. Ищем по датам и суммам зачислений на неё.
        incoming = {(row.date, row.amount) for row in account_rows if row.dds == DDS_TRANSFER_IN}
        sources: Counter[str] = Counter(
            row.account
            for row in rows
            if row.dds == DDS_TRANSFER_OUT and (row.date, row.amount) in incoming and row.account != name
        )
        envelopes[name] = sources.most_common(1)[0][0] if sources else None

    return envelopes


def build_plan(transactions_csv: str, collapse_envelopes: bool = True) -> ImportPlan:
    """Собирает полную картину переноса, ничего не записывая.

    Отчёт нужен до импорта, а не после: человек должен увидеть, что 133
    перевода склеились, восемь записей поедут как «не учитывать», а
    стартовое внесение станет остатком счёта — и только потом согласиться.
    """
    plan = ImportPlan()
    rows, issues = parse_transactions_csv(transactions_csv)
    plan.issues.extend(issues)

    # Счета-копилки распускаются в цели: сам счёт не создаётся, а переводы
    # на него и с него отбрасываются — они не двигали настоящих денег.
    envelopes = detect_envelope_accounts(rows) if collapse_envelopes else {}
    plan.envelopes = envelopes
    plan.credit_accounts = detect_credit_accounts(rows)

    for row in rows:
        plan.accounts.setdefault(row.account, Decimal("0"))
        if row.participant:
            plan.participants.add(row.participant)
        if row.unit:
            plan.units.add(row.unit)
        if row.goal:
            plan.goals.add(row.goal)
        if row.category and row.subcategory:
            plan.categories[row.category].add(row.subcategory)
        elif row.category:
            plan.categories.setdefault(row.category, set())

    for row in rows:
        if row.dds == DDS_INCOME:
            # Стартовое внесение — не доход, а остаток счёта на начало учёта.
            if OPENING_MARKER in row.description.lower():
                plan.openings.append(row)
                plan.accounts[row.account] = plan.accounts.get(row.account, Decimal("0")) + row.amount
            else:
                plan.incomes.append(row)
        elif row.dds == DDS_EXPENSE:
            plan.expenses.append(row)
        elif row.dds == DDS_RESERVE:
            plan.reserves.append(row)
        elif row.dds == DDS_RELEASE:
            plan.releases.append(row)
        elif row.dds in {DDS_TRANSFER_IN, DDS_TRANSFER_OUT}:
            continue  # обрабатываются парами ниже
        else:
            plan.issues.append(ImportIssue(row=row.row, reason="unknown_dds", detail=row.dds))

    pairs, transfer_issues = match_transfers(rows)
    plan.issues.extend(transfer_issues)

    # Схлопывание копилки делается ПОСЛЕ склейки пар, а не построчно.
    # Построчная версия сопоставляла половины по «дате и сумме», и когда в
    # один день проходило несколько переводов на одинаковую сумму с разных
    # счетов, половины склеивались не с теми — на кредитке оставался долг,
    # которого не было. У готовой пары обе стороны известны точно.
    if envelopes:
        collapsed: list[tuple[ParsedTransaction, ParsedTransaction]] = []
        for outgoing, incoming in pairs:
            out_home = envelopes.get(outgoing.account)
            in_home = envelopes.get(incoming.account)

            if out_home is None and in_home is None:
                collapsed.append((outgoing, incoming))
                continue

            # Обе стороны сводятся к одному и тому же счёту — деньги никуда
            # не двигались, это была пометка «отложено».
            source = out_home or outgoing.account
            target = in_home or incoming.account
            if source == target:
                continue

            # Движение настоящее (например, с кредитки): сторону копилки
            # заменяем домашним счётом, куда деньги и попали.
            collapsed.append(
                (
                    replace(outgoing, account=source),
                    replace(incoming, account=target),
                )
            )
        pairs = collapsed

        # Счёт копилки не должен остаться в списке: на нём числятся только
        # операции откладывания, которые станут движениями по целям.
        for name in envelopes:
            plan.accounts.pop(name, None)

    plan.transfers = pairs

    return plan


def transaction_type_for(dds: str) -> TransactionType | None:
    """Тип операции Aurum-Ex по виду ДДС из таблицы."""
    if dds == DDS_INCOME:
        return TransactionType.INCOME
    if dds == DDS_EXPENSE:
        return TransactionType.EXPENSE
    if dds in {DDS_TRANSFER_IN, DDS_TRANSFER_OUT}:
        return TransactionType.TRANSFER
    return None


# Палитра для новых категорий — те же восемь слотов, что использует
# засев по умолчанию, чтобы импортированные категории не выбивались из
# оформления остальных.
_PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#e6c229", "#c2417d", "#7a5cd6", "#008300", "#898781"]


def _next_color(index: int) -> str:
    return _PALETTE[index % len(_PALETTE)]


def _rows_of(plan: ImportPlan) -> list[ParsedTransaction]:
    """Все разобранные строки плана — нужны, чтобы найти дату первой
    операции по счёту."""
    rows = [*plan.incomes, *plan.expenses, *plan.reserves, *plan.releases, *plan.openings]
    for outgoing, incoming in plan.transfers:
        rows.extend((outgoing, incoming))
    return rows


# Слова, по которым узнаётся статья «проценты по кредиту». Именно проценты, а
# не погашение: погашение уходит С обычного счёта, а проценты начисляются НА
# кредитный — поэтому только они и указывают на нужный счёт.
_INTEREST_WORDS = ("процент", "переплат")
_CREDIT_WORDS = ("кредит", "рассрочк", "займ")


def detect_credit_accounts(rows: list[ParsedTransaction]) -> set[str]:
    """Счета, на которых начисляются проценты по кредиту.

    Название счёта — ненадёжный признак: «Маркет Кредит» о себе говорит, а
    «Маркет 2222» молчит, хотя проценты начисляются и на него. Данные говорят
    прямее: если на счёт легла статья «Проценты по кредитам», это кредитный
    счёт, как бы он ни назывался.

    Погашение для этого не годится: оно списывается с обычного счёта, с
    которого платят, и по нему кредитным оказался бы как раз не тот.

    Результат — подсказка, а НЕ решение: вид счёта по нему не меняется.
    Правило ошибается легко: с дебетовой карты тоже можно один раз
    заплатить проценты по рассрочке, и карта выглядит кредитной. Кто из них
    кредитный, знает владелец; приложение только показывает, где посмотреть.
    """
    credit_accounts: set[str] = set()
    for row in rows:
        text = f"{row.category or ''} {row.subcategory or ''}".lower()
        if any(word in text for word in _INTEREST_WORDS) and any(
            word in text for word in _CREDIT_WORDS
        ):
            credit_accounts.add(row.account)
    return credit_accounts


def _guess_account_kind(name: str) -> AccountKind:
    """Вид счёта по его названию.

    Догадка, а не истина: в таблице вида счёта не было вовсе, и лучше
    предложить осмысленный вариант, чем свалить всё в «прочее». Человек
    поправит шесть счетов за минуту, а вот полтора десятка категорий
    вручную разбирать не станет.
    """
    lowered = name.lower()
    if "cr " in lowered or "credit" in lowered or "кредит" in lowered:
        return AccountKind.CREDIT_CARD
    if "наличн" in lowered or "cash" in lowered:
        return AccountKind.CASH
    if "imaginary" in lowered or "мнимый" in lowered:
        # Фиктивный счёт для отложенных денег. В новой модели его роль
        # исполняют цели с резервом внутри счёта, но сам счёт переносится:
        # на нём висят операции, и удалять его значило бы потерять историю.
        return AccountKind.OTHER
    return AccountKind.CHECKING


def _guess_account_nature(name: str) -> AccountNature:
    """Актив или обязательство — по названию счёта.

    Найденные в данных проценты по кредиту сюда НЕ входят, хотя соблазн был.
    Правило «на счёт начисляли проценты → это кредитный счёт» легко даёт
    неверный ответ: с дебетовой карты тоже можно один раз заплатить
    проценты по рассрочке, и карта уехала бы в обязательства.

    Проценты по-прежнему находятся (см. detect_credit_accounts) и
    показываются в отчёте перед импортом как подсказка. Но применяет её
    человек: он знает, что у него за счёт, а приложение только догадывается,
    и молча угаданная неправда хуже честного вопроса.
    """
    kind = _guess_account_kind(name)
    return AccountNature.LIABILITY if kind is AccountKind.CREDIT_CARD else AccountNature.ASSET


def _guess_category_kind(name: str, plan: ImportPlan) -> CategoryKind:
    """Доходная категория или расходная — по тому, в каких операциях она
    реально встречается. Название об этом не говорит: «Долги — Возврат» это
    доход, а «Долги — Погашение» расход.

    Решает большинство, а не единственное совпадение. В настоящей таблице
    у «Прочих расходов» 179 расходных строк и одна доходная — человек
    однажды промахнулся видом операции, — и правило «есть хоть один доход →
    категория доходная» переносило всю ветку не на ту сторону: расход на
    восемьдесят тысяч оказывался доходом.

    При равенстве выбирается расход. Ошибка в эту сторону безобиднее:
    завышенный доход искажает представление человека о себе сильнее, чем
    завышенный расход.
    """
    income_rows = sum(1 for row in plan.incomes if row.category == name)
    expense_rows = sum(1 for row in plan.expenses if row.category == name)
    return CategoryKind.INCOME if income_rows > expense_rows else CategoryKind.EXPENSE


async def apply_plan(
    session: AsyncSession,
    plan: ImportPlan,
    base_currency: str,
    settings: SheetSettings | None = None,
) -> ImportResult:
    """Записывает план в базу одной транзакцией.

    Порядок важен: сначала справочники, потом счета с начальными остатками,
    потом операции — у каждой из них есть ссылки на всё перечисленное.

    Ничего не коммитится по ходу: либо переносится вся история, либо не
    переносится ничего. Половина истории хуже, чем её отсутствие, — по ней
    нельзя понять, чего не хватает.
    """
    result = ImportResult(issues=list(plan.issues))

    # Категории по умолчанию, засеянные при первом запуске, удаляются: своё
    # дерево из таблицы полнее и понятнее человеку, а рядом с ним английские
    # "Groceries" и "Dining Out" — просто мусор, который придётся вычищать
    # руками. Удаляются только нетронутые: если на категорию уже успели
    # что-то записать, она остаётся.
    # Стартовый счёт, созданный засевом, тоже лишний рядом со своими
    # счетами из таблицы. Удаляется только пустой: если на нём уже успели
    # что-то записать, он остаётся.
    for account in (await session.execute(select(Account))).scalars().all():
        used = (
            await session.execute(
                select(func.count())
                .select_from(Transaction)
                .where(
                    (Transaction.account_id == account.id)
                    | (Transaction.transfer_account_id == account.id)
                )
            )
        ).scalar_one()
        if not used and account.name not in plan.accounts:
            await session.delete(account)
    await session.flush()

    default_categories = (
        await session.execute(select(Category).where(Category.is_default.is_(True)))
    ).scalars().all()
    for category in default_categories:
        used = (
            await session.execute(
                select(func.count()).select_from(Transaction).where(Transaction.category_id == category.id)
            )
        ).scalar_one()
        if not used:
            await session.delete(category)
    await session.flush()

    # --- Справочники ---

    known_currencies = settings.account_currencies if settings else {}

    accounts: dict[str, Account] = {}
    for name, opening in plan.accounts.items():
        # Счёт-копилка не создаётся: его роль исполняют цели с резервом
        # внутри настоящего счёта (см. detect_envelope_accounts).
        if name in plan.envelopes:
            continue
        nature = _guess_account_nature(name)
        account = Account(
            name=name,
            kind=_guess_account_kind(name),
            nature=nature,
            # Валюта счёта берётся из листа настроек, если он приложен: там
            # она указана прямо, а догадываться по названию неоткуда.
            currency=known_currencies.get(name, base_currency),
            opening_balance=opening,
            # Начальный остаток действует с первой операции по этому счёту.
            opening_date=min((row.date for row in _rows_of(plan) if row.account == name), default=None),
            # Кредитному счёту минус разрешён: это и есть долг.
            allow_negative=nature is AccountNature.LIABILITY,
        )
        session.add(account)
        accounts[name] = account
    await session.flush()
    result.accounts = len(accounts)

    participants: dict[str, Participant] = {}
    # Участники берутся и из операций, и из листа настроек: в настройках
    # перечислены все заведённые, включая тех, на кого пока ничего не
    # записано, а в операциях — только реально встречавшиеся.
    participant_names = set(plan.participants)
    pet_names: set[str] = set()
    if settings:
        participant_names.update(settings.participants)
        pet_names.update(settings.pets)
        participant_names -= pet_names

    for name in sorted(participant_names):
        participant = Participant(name=name, kind=ParticipantKind.PERSON)
        session.add(participant)
        participants[name] = participant
    for name in sorted(pet_names):
        participant = Participant(name=name, kind=ParticipantKind.PET)
        session.add(participant)
        participants[name] = participant

    # Магазины и единицы измерения — справочники, которые в операциях не
    # упоминаются напрямую, но пригодятся сразу после импорта.
    if settings:
        for store_name in settings.stores:
            session.add(Store(name=store_name))

    # Категории переносятся деревом: верхний уровень из «Категория ДДС»,
    # вложенный — из «Подкатегории ДДС». Ограничение в один уровень было у
    # таблицы, а не у нас, поэтому дерево можно углублять и дальше.
    categories: dict[tuple[str, str | None], Category] = {}
    # Раскладка добавляет промежуточные уровни поверх плоской пары
    # «категория — подкатегория» (см. services/category_grouping.py).
    #
    # Всё адресуется парой (ветка, лист), а не именем: имена в этом дереве
    # не уникальны. В настоящей таблице есть ветка «Вода» с подкатегорией
    # «Вода» — так помечали трату на ветку без уточнения, — и раскладка по
    # именам сделала бы категорию родителем самой себе.
    nesting = build_nesting({name: sorted(children) for name, children in plan.categories.items()})

    kind_by_branch: dict[str, CategoryKind] = {}
    color_by_branch: dict[str, str] = {}
    for index, branch_name in enumerate(plan.categories):
        kind_by_branch[branch_name] = _guess_category_kind(branch_name, plan)
        color_by_branch[branch_name] = _next_color(index)

    def branch_of(level_name: str) -> str | None:
        """Ветка, к которой относится новый промежуточный уровень.

        Новый уровень собственных операций не имеет, и вид с цветом брать
        ему неоткуда, кроме как у того, что под ним лежит. Иначе ветка
        окажется наполовину доходной.
        """
        parent = nesting.new_levels.get(level_name)
        if parent in kind_by_branch:
            return parent
        for branch, super_parent in nesting.branch_parent.items():
            if super_parent == level_name:
                return branch
        return None

    created_levels: dict[str, Category] = {}
    # Сначала новые верхние уровни, потом группы внутри веток: у второго
    # родитель — сама ветка, а она создаётся между ними.
    for level_name, parent_name in nesting.new_levels.items():
        if parent_name is not None:
            continue
        source = branch_of(level_name)
        level = Category(
            name=level_name,
            kind=kind_by_branch.get(source, CategoryKind.EXPENSE),
            parent_id=None,
            color=color_by_branch.get(source, _next_color(len(created_levels))),
            is_default=False,
        )
        session.add(level)
        created_levels[level_name] = level
    await session.flush()

    branches: dict[str, Category] = {}
    for branch_name, children in plan.categories.items():
        super_parent = nesting.branch_parent.get(branch_name)
        branch = Category(
            name=branch_name,
            kind=kind_by_branch[branch_name],
            parent_id=created_levels[super_parent].id if super_parent in created_levels else None,
            color=color_by_branch[branch_name],
            is_default=False,
        )
        session.add(branch)
        branches[branch_name] = branch
    await session.flush()

    groups: dict[str, Category] = {}
    for level_name, parent_name in nesting.new_levels.items():
        if parent_name is None or parent_name not in branches:
            continue
        group = Category(
            name=level_name,
            kind=kind_by_branch[parent_name],
            parent_id=branches[parent_name].id,
            color=color_by_branch[parent_name],
            is_default=False,
        )
        session.add(group)
        groups[level_name] = group
    await session.flush()

    total_levels = len(created_levels) + len(branches) + len(groups)
    for branch_name, children in plan.categories.items():
        categories[(branch_name, None)] = branches[branch_name]
        for child_name in sorted(children):
            group_name = nesting.leaf_group.get((branch_name, child_name))
            holder = groups[group_name] if group_name in groups else branches[branch_name]
            child = Category(
                name=child_name,
                kind=kind_by_branch[branch_name],
                parent_id=holder.id,
                color=color_by_branch[branch_name],
                is_default=False,
            )
            session.add(child)
            categories[(branch_name, child_name)] = child
            total_levels += 1

    await session.flush()
    result.categories = total_levels
    result.participants = len(participants)

    goals: dict[str, Goal] = {}
    # Счёт, на котором физически лежат отложенные деньги. Берётся у копилки,
    # которую распустили: именно с него на неё и переводили.
    envelope_home = next(
        (accounts[home] for home in plan.envelopes.values() if home and home in accounts),
        None,
    )
    for name in sorted(plan.goals):
        # Целевая сумма в таблице не хранилась — только взносы. Ставим
        # сумму фактически отложенного: цель уже прожита, и придумывать ей
        # план задним числом было бы враньём.
        reserved = sum(
            (row.amount for row in plan.reserves if row.goal == name),
            Decimal("0"),
        )
        # Дата закрытия — последний возврат по этой цели: именно тогда
        # накопленное потратили. Без неё завершённая цель выглядит
        # закрытой сегодня, хотя закрыли её два года назад.
        closed = max(
            (row.date for row in plan.releases if row.goal == name),
            default=None,
        )
        goal = Goal(
            name=name,
            target_amount=reserved or Decimal("0"),
            status=GoalStatus.ACHIEVED,
            account_id=envelope_home.id if envelope_home is not None else None,
            closed_at=closed,
        )
        session.add(goal)
        goals[name] = goal
    await session.flush()
    result.goals = len(goals)

    # --- Операции ---

    # Номер в пределах дня — сквозной по всем счетам, как и при обычном
    # вводе (см. services/transaction_service.py, next_day_order). Иначе у
    # покупки наличными и покупки картой в один день оказался бы один и тот
    # же номер, и переставить их относительно друг друга стало бы нельзя.
    day_orders: dict[date_, int] = defaultdict(int)

    def next_order(on_date: date_) -> int:
        order = day_orders[on_date]
        day_orders[on_date] = order + 1
        return order

    def category_for(row: ParsedTransaction) -> Category | None:
        if row.category and row.subcategory:
            return categories.get((row.category, row.subcategory))
        if row.category:
            return categories.get((row.category, None))
        return None

    def make(row: ParsedTransaction, tx_type: TransactionType, **extra) -> Transaction:
        account = accounts[row.account]
        category = category_for(row) if tx_type in {TransactionType.INCOME, TransactionType.EXPENSE} else None
        transaction = Transaction(
            account_id=account.id,
            category_id=category.id if category is not None else None,
            type=tx_type,
            amount=row.amount,
            currency=base_currency,
            exchange_rate=Decimal("1"),
            amount_base=row.amount,
            description=row.description,
            date=row.date,
            day_order=next_order(row.date),
            is_excluded=row.is_excluded,
            participant_id=participants[row.participant].id if row.participant in participants else None,
            **extra,
        )
        session.add(transaction)
        return transaction

    for row in plan.incomes:
        make(row, TransactionType.INCOME)
    for row in plan.expenses:
        make(row, TransactionType.EXPENSE)
    result.transactions = len(plan.incomes) + len(plan.expenses)

    for outgoing, incoming in plan.transfers:
        # Пара строк схлопывается в одну запись перевода: счёт-источник от
        # списания, счёт-получатель от зачисления.
        make(
            outgoing,
            TransactionType.TRANSFER,
            transfer_account_id=accounts[incoming.account].id,
        )
    result.transfers = len(plan.transfers)

    # Взносы в цели: в таблице они лежали на фиктивном счёте, здесь
    # становятся записями журнала цели. Сам фиктивный счёт остаётся в
    # списке счетов — на нём висят операции, и удалять его значило бы
    # потерять историю.
    # Счёт у каждого взноса, а не только у цели: резерв ведётся по счетам,
    # и без него отложенное не привязано ни к одному остатку.
    envelope_account_id = envelope_home.id if envelope_home is not None else None
    for row in plan.reserves:
        goal = goals.get(row.goal or "")
        if goal is None:
            continue
        session.add(
            GoalContribution(
                goal_id=goal.id,
                amount=row.amount,
                date=row.date,
                note=row.description,
                account_id=envelope_account_id,
            )
        )
    for row in plan.releases:
        goal = goals.get(row.goal or "")
        if goal is None:
            continue
        session.add(
            GoalContribution(
                goal_id=goal.id,
                amount=-row.amount,
                date=row.date,
                note=row.description,
                account_id=envelope_account_id,
            )
        )
    result.goal_contributions = len(plan.reserves) + len(plan.releases)

    # Рабочие часы. В таблице они годовые, а нужны помесячные — раскладываем
    # поровну, но ТОЛЬКО по месяцам, где есть операции. Это и есть починка
    # исходной ошибки: год, в котором учёт вёлся пять месяцев, делил годовую
    # норму часов на весь год и занижал стоимость часа в два с лишним раза.
    if settings and settings.work_hours_by_year:
        months_by_year: dict[int, set[int]] = defaultdict(set)
        for row in _rows_of(plan):
            months_by_year[row.date.year].add(row.date.month)

        for year, hours in settings.work_hours_by_year.items():
            months = sorted(months_by_year.get(year, set()))
            if not months:
                continue
            per_month = (hours / len(months)).quantize(Decimal("0.01"))
            workdays = settings.workdays_by_year.get(year)
            per_month_days = round(workdays / len(months)) if workdays else None
            for month in months:
                session.add(
                    WorkPeriod(year=year, month=month, hours=per_month, workdays=per_month_days)
                )
        result.work_periods = sum(len(months) for months in months_by_year.values())

    await session.commit()
    return result
