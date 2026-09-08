"""Month-by-month income vs. expense — the multi-month view neither the
Dashboard (locked to one month) nor Reports (one category at a time, or a
category ranking) answers on its own. Transfers between the user's own
accounts are excluded from both totals, same as the Dashboard breakdown.

Начальные остатки счетов входят в оборот. Деньги, лежавшие на счёте до
первой записи, тоже были когда-то заработаны — просто раньше, чем начался
учёт, — и выбросить их значит показать сальдо, которое не сходится с
остатком на счетах. Отрицательный начальный остаток (счёт открыт с долгом)
попадает в расход: направление денег важнее удобной подписи.
"""
from collections import defaultdict
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.services.transaction_service import counted_only, earnings_and_spending_only
from app.schemas.cash_flow import CashFlowPoint, CashFlowResponse


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


async def get_cash_flow(
    session: AsyncSession, start_date: date_ | None, end_date: date_ | None
) -> CashFlowResponse:
    bounds_stmt = select(func.min(Transaction.date), func.max(Transaction.date)).where(
        earnings_and_spending_only(),
        counted_only(),
    )
    if start_date:
        bounds_stmt = bounds_stmt.where(Transaction.date >= start_date)
    if end_date:
        bounds_stmt = bounds_stmt.where(Transaction.date <= end_date)
    min_date, max_date = (await session.execute(bounds_stmt)).one()

    # Начальные остатки: сумма и дата, с которой счёт считается открытым.
    # Нулевые не берём — они ничего не добавляют, но растянули бы диапазон.
    openings = [
        (opening_date, amount)
        for opening_date, amount in (
            await session.execute(
                select(Account.opening_date, Account.opening_balance).where(
                    Account.opening_balance.is_not(None),
                    Account.opening_balance != 0,
                )
            )
        ).all()
    ]

    # Диапазон расширяется до самого раннего остатка: счёт мог быть открыт
    # раньше первой записи, и обрезать его значило бы потерять деньги, с
    # которых всё началось.
    opening_dates = [date for date, _ in openings if date is not None]
    if opening_dates:
        earliest_opening = min(opening_dates)
        if min_date is None or earliest_opening < min_date:
            min_date = earliest_opening
        # И до самого позднего: без единой операции остаток — это всё, что
        # вообще произошло, и не показать его значит показать пустоту вместо
        # денег, которые на счёте лежат.
        latest_opening = max(opening_dates)
        if max_date is None or latest_opening > max_date:
            max_date = latest_opening

    effective_start = start_date or min_date
    effective_end = end_date or max_date

    empty = CashFlowResponse(
        start_date=effective_start,
        end_date=effective_end,
        points=[],
        total_income=Decimal("0"),
        total_expense=Decimal("0"),
        total_net=Decimal("0"),
    )
    if effective_start is None or effective_end is None:
        return empty

    rows_stmt = (
        select(
            extract("year", Transaction.date).label("year"),
            extract("month", Transaction.date).label("month"),
            Transaction.type,
            func.sum(Transaction.amount).label("amount"),
        )
        .where(
            earnings_and_spending_only(),
            counted_only(),
            Transaction.date >= effective_start,
            Transaction.date <= effective_end,
        )
        .group_by("year", "month", Transaction.type)
    )
    rows = (await session.execute(rows_stmt)).all()

    by_month: dict[tuple[int, int], dict[TransactionType, Decimal]] = defaultdict(dict)
    for year, month, tx_type, amount in rows:
        by_month[(int(year), int(month))][tx_type] = amount

    # Остатки раскладываются по месяцам открытия счетов. Счёт без даты
    # открытия относится к первому месяцу диапазона: «до начала учёта» — это
    # и есть его начало, а выбросить остаток нельзя.
    opening_by_month: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    for opening_date, amount in openings:
        moment = opening_date or effective_start
        if not (effective_start <= moment <= effective_end):
            # За пределами выбранного периода: при фильтре «2026 год» остаток
            # 2022-го показывать неоткуда.
            continue
        opening_by_month[(moment.year, moment.month)] += amount

    points: list[CashFlowPoint] = []
    year, month = effective_start.year, effective_start.month
    while (year, month) <= (effective_end.year, effective_end.month):
        totals = by_month.get((year, month), {})
        income = totals.get(TransactionType.INCOME, Decimal("0"))
        expense = totals.get(TransactionType.EXPENSE, Decimal("0"))
        opening = opening_by_month.get((year, month), Decimal("0"))
        # Знак решает, в какую сторону попадёт остаток. Счёт, открытый с
        # долгом, — это не отрицательный доход, а расход.
        if opening >= 0:
            income += opening
        else:
            expense += -opening
        points.append(
            CashFlowPoint(
                year=year,
                month=month,
                income=income,
                expense=expense,
                net=income - expense,
                opening=opening,
            )
        )
        year, month = _next_month(year, month)

    total_income = sum((p.income for p in points), Decimal("0"))
    total_expense = sum((p.expense for p in points), Decimal("0"))

    return CashFlowResponse(
        start_date=effective_start,
        end_date=effective_end,
        points=points,
        total_income=total_income,
        total_expense=total_expense,
        total_net=total_income - total_expense,
        total_opening=sum((p.opening for p in points), Decimal("0")),
    )
