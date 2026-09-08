"""Сводка дашборда.

Период выбирается: месяц, год или всё время. Месяц как единственная рамка —
то, чем неудобна была исходная таблица: годовые итоги там приходилось
собирать отдельным листом, а вопрос «сколько всего заработано за четыре
года» не имел ответа вовсе.

Остатки по счетам показываются текущие независимо от периода. Вопрос
«сколько у меня сейчас» от выбора периода не зависит, и подменять ответ
остатком на конец марта значило бы врать ровно тому, кто открыл дашборд,
чтобы понять, сколько у него денег.
"""
import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.models.work_period import WorkPeriod
from app.schemas.dashboard import (
    AccountBalanceItem,
    CategoryBreakdownChildItem,
    CategoryBreakdownItem,
    DashboardSummary,
    LargestTransactionItem,
    MonthPoint,
)
from app.services.account_service import get_balances_by_account
from app.services.cash_flow_service import get_cash_flow
from app.services.currency_service import quantize_money
from app.services.hourly_service import elapsed_hours
from app.services.category_rollup import rollup_spending_by_top_level_category
from app.services.settlement_service import get_reserved_by_account
from app.services.transaction_service import counted_only

# Categorical slots are capped at 8 (dataviz skill: a 9th series folds into "Other",
# never a generated hue) — this is also the exact size of the default category set.
MAX_CHART_SLICES = 8
OTHER_SLICE_COLOR = "#898781"  # muted ink, reserved for the non-categorical rollup


# Сколько самых крупных трат показывать. Пять помещается на экран телефона
# без прокрутки и почти всегда объясняет месяц.
LARGEST_COUNT = 5


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


async def _period_bounds(
    session: AsyncSession, range_key: str, year: int, month: int
) -> tuple[date | None, date | None]:
    """Границы выбранного периода.

    Для «за всё время» границы берутся из самих данных, а не ставятся
    заведомо широкими: интерфейс должен показать, за что именно посчитано, а
    «с 1970 года» — не ответ.
    """
    if range_key == "month":
        return _month_bounds(year, month)
    if range_key == "year":
        return date(year, 1, 1), date(year, 12, 31)
    bounds = (
        await session.execute(
            select(func.min(Transaction.date), func.max(Transaction.date)).where(counted_only())
        )
    ).one()
    start, end = bounds[0], bounds[1]

    # Счёт мог быть открыт раньше первой записи. Начать «всё время» позже
    # даты открытия значит объявить началом истории момент, когда деньги на
    # счёте уже лежали.
    earliest_opening = (
        await session.execute(
            select(func.min(Account.opening_date)).where(
                Account.opening_date.is_not(None), Account.opening_balance != 0
            )
        )
    ).scalar_one()
    if earliest_opening is not None and (start is None or earliest_opening < start):
        start = earliest_opening
        if end is None:
            end = earliest_opening
    return start, end


async def _accounts_block(session: AsyncSession) -> list[AccountBalanceItem]:
    balances = await get_balances_by_account(session)
    reserved_by_account = await get_reserved_by_account(session)
    accounts = (
        (await session.execute(select(Account).where(Account.is_archived.is_(False)).order_by(Account.name)))
        .scalars()
        .all()
    )
    items: list[AccountBalanceItem] = []
    for account in accounts:
        balance = balances.get(account.id, Decimal("0"))
        reserved = reserved_by_account.get(account.id, Decimal("0"))
        items.append(
            AccountBalanceItem(
                account_id=account.id,
                name=account.name,
                balance=balance,
                reserved=reserved,
                # Резерв не уменьшает баланс: деньги лежат там же, просто
                # часть обещана цели.
                available=max(balance - reserved, Decimal("0")),
                nature=account.nature.value,
            )
        )
    # Сначала счета с деньгами: пустые и кредитные внизу, потому что вопрос
    # «где мои деньги» задают про первые.
    return sorted(items, key=lambda item: -item.balance)


async def _hourly_block(
    session: AsyncSession, start: date | None, end: date | None, real_income: Decimal
) -> tuple[Decimal | None, Decimal | None]:
    """Заработок за час работы.

    Смысл не в самой цифре, а в переводе покупок на язык времени: «этот
    монитор стоил мне четыре дня» доходит быстрее, чем «17 273 рубля».

    None, когда за период не введено ни часа: делить на ноль нечестнее, чем
    не показывать.
    """
    stmt = select(WorkPeriod.year, WorkPeriod.month, WorkPeriod.hours)
    if start is not None:
        # Месяц считается попавшим в период, если его номер не раньше
        # начального: часы вводятся помесячно, дробить их нечем.
        stmt = stmt.where(
            (WorkPeriod.year > start.year)
            | ((WorkPeriod.year == start.year) & (WorkPeriod.month >= start.month))
        )
    if end is not None:
        stmt = stmt.where(
            (WorkPeriod.year < end.year) | ((WorkPeriod.year == end.year) & (WorkPeriod.month <= end.month))
        )
    # У текущего месяца засчитывается только прошедшая доля введённых
    # часов: иначе первого числа доход за один день делится на месячный
    # план, и заработок за час выходит в рублях.
    hours = sum(
        (
            elapsed_hours(int(year), int(month), Decimal(total))
            for year, month, total in (await session.execute(stmt)).all()
            if total
        ),
        Decimal("0"),
    )
    if hours <= 0:
        return None, None
    # Округление до копейки: деление Decimal даёт хвост в двадцать знаков, и
    # отдавать его наружу значит заставлять каждого потребителя округлять
    # самому — а округлят все по-разному.
    return quantize_money(hours), quantize_money(real_income / hours)


async def _largest_block(
    session: AsyncSession, start: date | None, end: date | None
) -> list[LargestTransactionItem]:
    """Самые крупные траты периода.

    Обычно объясняют, куда ушли деньги, лучше любой диаграммы: круг из
    восьми долей отвечает «на что вообще», а этот список — «из-за чего
    именно в этом месяце».
    """
    stmt = (
        select(
            Transaction.id,
            Transaction.date,
            Transaction.description,
            Transaction.amount,
            Category.name,
            Account.name,
        )
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(Transaction.type == TransactionType.EXPENSE, counted_only())
        .order_by(Transaction.amount.desc())
        .limit(LARGEST_COUNT)
    )
    if start is not None:
        stmt = stmt.where(Transaction.date >= start)
    if end is not None:
        stmt = stmt.where(Transaction.date <= end)
    return [
        LargestTransactionItem(
            id=row[0],
            date=row[1],
            description=row[2],
            amount=row[3],
            category_name=row[4],
            account_name=row[5],
        )
        for row in (await session.execute(stmt)).all()
    ]


async def get_dashboard_summary(
    session: AsyncSession, year: int, month: int, range_key: str = "month"
) -> DashboardSummary:
    start, end = await _period_bounds(session, range_key, year, month)
    if start is None or end is None:
        # Ни одной операции. Сводка пустая, но счета показываются: они могут
        # существовать с начальным остатком и без единой записи.
        return DashboardSummary(
            year=year,
            month=month,
            start_date=None,
            end_date=None,
            real_income=Decimal("0"),
            spent=Decimal("0"),
            net=Decimal("0"),
            transferred_out=Decimal("0"),
            spending_by_category=[],
            accounts=await _accounts_block(session),
        )

    totals_stmt = (
        select(Transaction.type, func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.date >= start, Transaction.date <= end, counted_only())
        .group_by(Transaction.type)
    )
    totals_result = await session.execute(totals_stmt)
    totals: dict[TransactionType, Decimal] = {row[0]: row[1] for row in totals_result.all()}

    real_income = totals.get(TransactionType.INCOME, Decimal("0"))
    spent = totals.get(TransactionType.EXPENSE, Decimal("0"))
    transferred_out = totals.get(TransactionType.TRANSFER, Decimal("0"))

    # A subcategory's spending rolls up into its parent's slice, and a split
    # transaction's category_id=NULL means its category lives on its split
    # lines instead — rollup_spending_by_top_level_category handles both
    # the same way a plain transaction's category already was.
    rows = await rollup_spending_by_top_level_category(
        session, transaction_type=TransactionType.EXPENSE, start_date=start, end_date=end
    )

    top_rows, rest_rows = rows[:MAX_CHART_SLICES], rows[MAX_CHART_SLICES:]

    def _percent(amount: Decimal) -> float:
        return float(amount / spent * 100) if spent else 0.0

    spending_by_category = [
        CategoryBreakdownItem(
            category_id=row.category_id, name=row.name, color=row.color, icon=row.icon,
            amount=row.amount, percent=_percent(row.amount),
            children=[
                CategoryBreakdownChildItem(
                    category_id=child.category_id, name=child.name, color=child.color, icon=child.icon,
                    amount=child.amount,
                )
                for child in row.children
            ],
        )
        for row in top_rows
    ]

    if rest_rows:
        other_amount = sum((row.amount for row in rest_rows), Decimal("0"))
        spending_by_category.append(
            CategoryBreakdownItem(
                category_id=None, name="Other", color=OTHER_SLICE_COLOR, icon="more-horizontal",
                amount=other_amount, percent=_percent(other_amount),
            )
        )

    hours_worked, earned_per_hour = await _hourly_block(session, start, end, real_income)
    # Помесячная картина берётся из того же расчёта, что и страница движения
    # денег: два разных ответа на один вопрос — худшее, что приложение может
    # показать про деньги.
    cash_flow = await get_cash_flow(session, start, end)

    return DashboardSummary(
        year=year,
        month=month,
        start_date=start,
        end_date=end,
        real_income=real_income,
        spent=spent,
        net=real_income - spent,
        transferred_out=transferred_out,
        spending_by_category=spending_by_category,
        accounts=await _accounts_block(session),
        hours_worked=hours_worked,
        earned_per_hour=earned_per_hour,
        largest_expenses=await _largest_block(session, start, end),
        monthly=[
            MonthPoint(
                year=point.year,
                month=point.month,
                income=point.income,
                expense=point.expense,
                net=point.net,
            )
            for point in cash_flow.points
        ],
    )
