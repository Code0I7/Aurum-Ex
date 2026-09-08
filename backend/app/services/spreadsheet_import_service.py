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
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date as date_
from decimal import Decimal, InvalidOperation

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
from app.models.transaction import Transaction

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


@dataclass
class ImportPlan:
    """Что получится, если применить импорт. Собирается целиком до записи в
    базу, чтобы отчёт можно было показать до, а не после."""

    accounts: dict[str, Decimal] = field(default_factory=dict)
    categories: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    participants: set[str] = field(default_factory=set)
    units: set[str] = field(default_factory=set)
    goals: set[str] = field(default_factory=set)

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
                description=_clean(raw.get("Комментарий статьи Расходов или Доходов")) or "Без описания",
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


def build_plan(transactions_csv: str) -> ImportPlan:
    """Собирает полную картину переноса, ничего не записывая.

    Отчёт нужен до импорта, а не после: человек должен увидеть, что 133
    перевода склеились, восемь записей поедут как «не учитывать», а
    стартовое внесение станет остатком счёта — и только потом согласиться.
    """
    plan = ImportPlan()
    rows, issues = parse_transactions_csv(transactions_csv)
    plan.issues.extend(issues)

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
    plan.transfers = pairs
    plan.issues.extend(transfer_issues)

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
    kind = _guess_account_kind(name)
    return AccountNature.LIABILITY if kind is AccountKind.CREDIT_CARD else AccountNature.ASSET


def _guess_category_kind(name: str, plan: ImportPlan) -> CategoryKind:
    """Доходная категория или расходная — по тому, в каких операциях она
    реально встречается. Название об этом не говорит: «Долги — Возврат» это
    доход, а «Долги — Погашение» расход."""
    in_income = any(row.category == name for row in plan.incomes)
    return CategoryKind.INCOME if in_income else CategoryKind.EXPENSE


async def apply_plan(session: AsyncSession, plan: ImportPlan, base_currency: str) -> ImportResult:
    """Записывает план в базу одной транзакцией.

    Порядок важен: сначала справочники, потом счета с начальными остатками,
    потом операции — у каждой из них есть ссылки на всё перечисленное.

    Ничего не коммитится по ходу: либо переносится вся история, либо не
    переносится ничего. Половина истории хуже, чем её отсутствие, — по ней
    нельзя понять, чего не хватает.
    """
    result = ImportResult(issues=list(plan.issues))

    # --- Справочники ---

    accounts: dict[str, Account] = {}
    for name, opening in plan.accounts.items():
        account = Account(
            name=name,
            kind=_guess_account_kind(name),
            nature=_guess_account_nature(name),
            currency=base_currency,
            opening_balance=opening,
            # Начальный остаток действует с первой операции по этому счёту.
            opening_date=min((row.date for row in _rows_of(plan) if row.account == name), default=None),
            allow_negative=_guess_account_nature(name) is AccountNature.LIABILITY,
        )
        session.add(account)
        accounts[name] = account
    await session.flush()
    result.accounts = len(accounts)

    participants: dict[str, Participant] = {}
    for name in sorted(plan.participants):
        participant = Participant(name=name, kind=ParticipantKind.PERSON)
        session.add(participant)
        participants[name] = participant

    # Категории переносятся деревом: верхний уровень из «Категория ДДС»,
    # вложенный — из «Подкатегории ДДС». Ограничение в один уровень было у
    # таблицы, а не у нас, поэтому дерево можно углублять и дальше.
    categories: dict[tuple[str, str | None], Category] = {}
    for parent_name, children in plan.categories.items():
        kind = _guess_category_kind(parent_name, plan)
        parent = Category(name=parent_name, kind=kind, color=_next_color(len(categories)), is_default=False)
        session.add(parent)
        categories[(parent_name, None)] = parent
        await session.flush()
        for child_name in sorted(children):
            child = Category(
                name=child_name,
                kind=kind,
                parent_id=parent.id,
                color=parent.color,
                is_default=False,
            )
            session.add(child)
            categories[(parent_name, child_name)] = child
    await session.flush()
    result.categories = len(categories)
    result.participants = len(participants)

    goals: dict[str, Goal] = {}
    for name in sorted(plan.goals):
        # Целевая сумма в таблице не хранилась — только взносы. Ставим
        # сумму фактически отложенного: цель уже прожита, и придумывать ей
        # план задним числом было бы враньём.
        reserved = sum(
            (row.amount for row in plan.reserves if row.goal == name),
            Decimal("0"),
        )
        goal = Goal(name=name, target_amount=reserved or Decimal("0"), status=GoalStatus.ACHIEVED)
        session.add(goal)
        goals[name] = goal
    await session.flush()
    result.goals = len(goals)

    # --- Операции ---

    day_orders: dict[tuple[int, date_], int] = defaultdict(int)

    def next_order(account: Account, on_date: date_) -> int:
        key = (account.id, on_date)
        order = day_orders[key]
        day_orders[key] = order + 1
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
            day_order=next_order(account, row.date),
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
    for row in plan.reserves:
        goal = goals.get(row.goal or "")
        if goal is None:
            continue
        session.add(GoalContribution(goal_id=goal.id, amount=row.amount, date=row.date, note=row.description))
    for row in plan.releases:
        goal = goals.get(row.goal or "")
        if goal is None:
            continue
        session.add(GoalContribution(goal_id=goal.id, amount=-row.amount, date=row.date, note=row.description))
    result.goal_contributions = len(plan.reserves) + len(plan.releases)

    await session.commit()
    return result
