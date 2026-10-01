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
from datetime import date as date_, timedelta
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.services.currency_service import to_base
from app.services.transaction_service import (
    converted_only,
    counted_only,
    earnings_and_spending_only,
)
from app.schemas.cash_flow import CashFlowPoint, CashFlowResponse, DayPoint


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
    #
    # Остаток лежит в валюте счёта, а оборот считается в валюте установки,
    # поэтому он приводится курсом дня открытия — как операция того же
    # дня. Счёт без даты открытия берёт сегодняшний курс: другой даты у его
    # денег нет. Курса нет — остаток в оборот не входит, как и операция без
    # курса.
    openings: list[tuple[date_ | None, Decimal]] = []
    for opening_date, amount, currency in (
        await session.execute(
            select(Account.opening_date, Account.opening_balance, Account.currency).where(
                Account.opening_balance.is_not(None),
                Account.opening_balance != 0,
            )
        )
    ).all():
        _, amount_base = await to_base(session, amount, currency, opening_date or date_.today())
        if amount_base is not None:
            openings.append((opening_date, amount_base))

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
            # В валюте установки: месяц складывает операции всех счетов.
            func.sum(Transaction.amount_base).label("amount"),
        )
        .where(
            earnings_and_spending_only(),
            counted_only(),
            converted_only(),
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
async def get_daily_flow(
    session: AsyncSession, start_date: date_, end_date: date_
) -> list[DayPoint]:
    """Приход и расход по каждому дню отрезка, включая пустые дни.

    Те же фильтры и та же валюта, что у месячного расчёта: это одна и та
    же величина, просто нарезанная мельче. Пустые дни остаются в ряду —
    выкинуть их значит сжать календарь и показать три траты подряд там,
    где между ними неделя.

    Начальные остатки раскладываются по дню открытия счёта. Счёт без даты
    открытия в дневной ряд не попадает: у месяца «до начала учёта» нет
    своего дня, и приписать остаток первому числу значило бы придумать
    событие, которого не было.
    """
    rows = (
        await session.execute(
            select(
                Transaction.date,
                Transaction.type,
                func.sum(Transaction.amount_base).label("amount"),
            )
            .where(
                earnings_and_spending_only(),
                counted_only(),
                converted_only(),
                Transaction.date >= start_date,
                Transaction.date <= end_date,
            )
            .group_by(Transaction.date, Transaction.type)
        )
    ).all()

    by_day: dict[date_, dict[TransactionType, Decimal]] = defaultdict(dict)
    for day, tx_type, amount in rows:
        by_day[day][tx_type] = amount

    opening_by_day: dict[date_, Decimal] = defaultdict(Decimal)
    for opening_date, amount, currency in (
        await session.execute(
            select(Account.opening_date, Account.opening_balance, Account.currency).where(
                Account.opening_balance.is_not(None),
                Account.opening_balance != 0,
                Account.opening_date.is_not(None),
                Account.opening_date >= start_date,
                Account.opening_date <= end_date,
            )
        )
    ).all():
        _, amount_base = await to_base(session, amount, currency, opening_date)
        if amount_base is not None:
            opening_by_day[opening_date] += amount_base

    points: list[DayPoint] = []
    day = start_date
    while day <= end_date:
        totals = by_day.get(day, {})
        income = totals.get(TransactionType.INCOME, Decimal("0"))
        expense = totals.get(TransactionType.EXPENSE, Decimal("0"))
        opening = opening_by_day.get(day, Decimal("0"))
        # Знак решает сторону, как и у месяца: счёт, открытый с долгом, —
        # это расход, а не отрицательный доход.
        if opening >= 0:
            income += opening
        else:
            expense += -opening
        points.append(
            DayPoint(date=day, income=income, expense=expense, net=income - expense, opening=opening)
        )
        day += timedelta(days=1)
    return points
