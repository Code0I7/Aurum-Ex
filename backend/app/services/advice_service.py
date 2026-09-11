"""Personalized, read-only financial advice — a curated set of insights
computed from data that already exists (transactions, budgets, category
totals). Unlike insights_service.py's proactive alerts (urgent, shown as a
banner on every page), these are advisory notes shown only on the dedicated
Advice page — a mix of positive, neutral, and cautionary tone, not just
warnings, and not something the user needs to act on immediately.
"""
import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.services.budget_service import get_budget_status
from app.services.transaction_service import counted_only
from app.schemas.advice import AdviceItem, AdviceResponse
from app.services.dashboard_service import get_dashboard_summary

TRAILING_MONTHS = 3
RISING_CATEGORY_THRESHOLD_PERCENT = 25
# В скольких из прошлых месяцев категория должна встречаться, чтобы среднее
# по ней что-то значило. Два из трёх: требовать все три значило бы молчать
# про сезонные траты, требовать один — сравнивать с числом, выдуманным из
# единственной покупки.
MIN_TRAILING_MONTHS = 2
# Насколько траты должны вырасти в рублях, а не только в процентах.
RISING_CATEGORY_MIN_DIFFERENCE = Decimal("500")
SAVINGS_RATE_TREND_THRESHOLD_POINTS = 5


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


async def _category_expense_totals(session: AsyncSession, year: int, month: int) -> dict[int, Decimal]:
    start, end = _month_bounds(year, month)
    stmt = (
        select(Transaction.category_id, func.sum(Transaction.amount))
        .where(
            Transaction.type == TransactionType.EXPENSE,
            counted_only(),
            Transaction.category_id.is_not(None),
            Transaction.date >= start,
            Transaction.date <= end,
        )
        .group_by(Transaction.category_id)
    )
    return {row[0]: row[1] for row in (await session.execute(stmt)).all()}


async def _rising_category_advice(session: AsyncSession, year: int, month: int) -> AdviceItem | None:
    """The expense category furthest above its own trailing-3-month average,
    if that's at least RISING_CATEGORY_THRESHOLD_PERCENT higher."""
    current_totals = await _category_expense_totals(session, year, month)
    if not current_totals:
        return None

    trailing_totals: dict[int, Decimal] = defaultdict(Decimal)
    # Сколько из прошлых месяцев в категории вообще что-то было. Среднее по
    # трём месяцам у категории, потраченной один раз, — это не среднее.
    months_seen: dict[int, int] = defaultdict(int)
    y, m = year, month
    for _ in range(TRAILING_MONTHS):
        y, m = _previous_month(y, m)
        for cat_id, amount in (await _category_expense_totals(session, y, m)).items():
            trailing_totals[cat_id] += amount
            months_seen[cat_id] += 1

    best: tuple[float, int, Decimal, Decimal] | None = None
    for cat_id, current in current_totals.items():
        seen = months_seen.get(cat_id, 0)
        # Нужна хотя бы пара месяцев подряд, иначе «выросли» сказать не о
        # чем. Раньше сумма делилась на три всегда: одна покупка на 56 ₽
        # три месяца назад давала «среднее» 18,67 ₽, и любая нормальная
        # трата после неё выглядела ростом на полторы тысячи процентов.
        # Совет при этом вытеснял настоящие изменения — он же самый
        # большой по проценту.
        if seen < MIN_TRAILING_MONTHS:
            continue
        # Делим на месяцы, в которых траты были, а не на длину окна:
        # пропущенный месяц означает «не покупали», а не «потратили ноль».
        average = trailing_totals[cat_id] / seen
        if average <= 0:
            continue
        difference = current - average
        # Абсолютный порог рядом с процентным. Рост со 120 ₽ до 200 ₽ — это
        # 67%, но говорить о нём не стоит: восемьдесят рублей не меняют
        # ни одного решения, а место в советах занимают.
        if difference < RISING_CATEGORY_MIN_DIFFERENCE:
            continue
        increase_percent = float(difference / average * 100)
        if increase_percent >= RISING_CATEGORY_THRESHOLD_PERCENT and (best is None or increase_percent > best[0]):
            best = (increase_percent, cat_id, current, average)

    if best is None:
        return None

    increase_percent, cat_id, current, average = best
    category = await session.get(Category, cat_id)
    if category is None:
        return None

    return AdviceItem(
        key="rising_category",
        tone="warning",
        params={
            "category": category.name,
            "percent": round(increase_percent),
            "current": float(current),
            "average": float(average),
        },
    )


async def _unbudgeted_top_category_advice(session: AsyncSession, year: int, month: int) -> AdviceItem | None:
    """This month's highest-spending expense category that has no budget.

    Лимит у категории может быть не только своим: категория с планом
    получает строку бюджета, выведенную из него (см. budget_service). Совет
    смотрел только в таблицу бюджетов и продолжал требовать завести бюджет
    там, где план уже был, — то есть просил завести вторую запись про ту же
    цифру.
    """
    current_totals = await _category_expense_totals(session, year, month)
    if not current_totals:
        return None

    status = await get_budget_status(session, year, month)
    budgeted_ids = {item.category_id for item in status.items}

    for cat_id, amount in sorted(current_totals.items(), key=lambda item: item[1], reverse=True):
        if cat_id in budgeted_ids:
            continue
        category = await session.get(Category, cat_id)
        if category is None:
            continue
        return AdviceItem(
            key="unbudgeted_top_category",
            tone="neutral",
            params={"category": category.name, "amount": float(amount)},
        )

    return None


async def _savings_rate_trend_advice(session: AsyncSession, year: int, month: int) -> AdviceItem | None:
    """This month's savings rate (net / real_income) vs. last month's, when
    the swing is large enough to be worth mentioning."""
    current = await get_dashboard_summary(session, year, month)
    prev_year, prev_month = _previous_month(year, month)
    previous = await get_dashboard_summary(session, prev_year, prev_month)

    if current.real_income <= 0 or previous.real_income <= 0:
        return None

    current_rate = float(current.net / current.real_income * 100)
    previous_rate = float(previous.net / previous.real_income * 100)
    diff = current_rate - previous_rate

    if abs(diff) < SAVINGS_RATE_TREND_THRESHOLD_POINTS:
        return None

    return AdviceItem(
        key="savings_rate_trend",
        tone="positive" if diff > 0 else "warning",
        params={"rate": round(current_rate), "diff": round(diff)},
    )


async def get_advice(session: AsyncSession) -> AdviceResponse:
    today = date.today()
    generators = (_rising_category_advice, _unbudgeted_top_category_advice, _savings_rate_trend_advice)

    items: list[AdviceItem] = []
    for generate in generators:
        item = await generate(session, today.year, today.month)
        if item is not None:
            items.append(item)

    return AdviceResponse(items=items)
