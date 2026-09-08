"""Proactive early-warning checks, computed from data that already exists.
Five signals: sustained negative monthly cash flow, a sustained net-worth
decline, one or more over-budget categories, too much capital in medium/high
risk tiers (the "80% at zero risk, 20% at most exposed" rule), and cash
sitting idle in a depository account. The first two only look at
fully-elapsed calendar months, so a same-month false alarm (rent already
paid, salary not landed yet) never fires — their "sustained for how long"
thresholds, the risk-allocation percentage, and the idle-cash amount/days are
all user-configurable (Settings page), stored on AppSettings, see
get_or_create_app_settings. The budget check is the opposite: it deliberately
looks at the CURRENT, still-in-progress month, since the whole point is to
catch overspending while there's still time to react.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.account import Account
from app.models.enums import AccountKind, TransactionType
from app.models.transaction import Transaction
from app.services.transaction_service import counted_only
from app.schemas.insights import AlertsResponse, FinancialAlert
from app.schemas.net_worth import NetWorthSummary
from app.services.budget_service import get_budget_status
from app.services.dashboard_service import get_dashboard_summary
from app.services.net_worth_service import get_net_worth_summary
from app.services.settings_service import get_or_create_app_settings

MAX_LOOKBACK_MONTHS = 24

# Accounts where a big, untouched balance means money isn't working — a
# credit card balance isn't "your cash", an investment account is already
# invested, and OTHER is too ambiguous to guess at.
_IDLE_CASH_ACCOUNT_TYPES = (AccountKind.CHECKING, AccountKind.SAVINGS, AccountKind.CASH)


def _previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


async def _negative_cash_flow_streak(session: AsyncSession) -> int:
    today = date.today()
    year, month = _previous_month(today.year, today.month)

    streak = 0
    for _ in range(MAX_LOOKBACK_MONTHS):
        summary = await get_dashboard_summary(session, year, month)
        if summary.net >= 0:
            break
        streak += 1
        year, month = _previous_month(year, month)
    return streak


def _net_worth_decline_streak(summary: NetWorthSummary) -> int:
    today = date.today()

    # Keep the last point seen for each (year, month) — `series` is ordered
    # ascending by date, so that's the month-end value — and drop the
    # current month, which is always partial.
    month_end: dict[tuple[int, int], Decimal] = {}
    for point in summary.series:
        if (point.date.year, point.date.month) == (today.year, today.month):
            continue
        month_end[(point.date.year, point.date.month)] = point.value

    ordered_months = sorted(month_end)
    if len(ordered_months) < 2:
        return 0

    streak = 0
    for i in range(len(ordered_months) - 1, 0, -1):
        if month_end[ordered_months[i]] < month_end[ordered_months[i - 1]]:
            streak += 1
        else:
            break
    return streak


async def _idle_cash_account_count(session: AsyncSession, threshold_amount: Decimal, threshold_days: int) -> int:
    eligible_ids = set(
        (
            await session.execute(
                select(Account.id).where(
                    Account.is_archived.is_(False), Account.kind.in_(_IDLE_CASH_ACCOUNT_TYPES)
                )
            )
        )
        .scalars()
        .all()
    )
    if not eligible_ids:
        return 0

    # Same derivation account_service.get_balances_by_account uses — balance is
    # never stored, only ever summed from the full transaction history — plus
    # tracking the most recent date that touched each account along the way.
    rows = await session.execute(
        select(
            Transaction.type,
            Transaction.amount,
            Transaction.account_id,
            Transaction.transfer_account_id,
            Transaction.date,
        ).where(counted_only())
    )
    balances: dict[int, Decimal] = defaultdict(Decimal)
    last_activity: dict[int, date] = {}

    def touch(account_id: int | None, tx_date: date) -> None:
        if account_id in eligible_ids and (account_id not in last_activity or tx_date > last_activity[account_id]):
            last_activity[account_id] = tx_date

    for tx_type, amount, account_id, transfer_account_id, tx_date in rows.all():
        if tx_type == TransactionType.INCOME:
            balances[account_id] += amount
        elif tx_type == TransactionType.EXPENSE:
            balances[account_id] -= amount
        elif tx_type == TransactionType.TRANSFER:
            balances[account_id] -= amount
            if transfer_account_id is not None:
                balances[transfer_account_id] += amount
        touch(account_id, tx_date)
        touch(transfer_account_id, tx_date)

    cutoff = date.today() - timedelta(days=threshold_days)
    return sum(
        1
        for account_id in eligible_ids
        if balances.get(account_id, Decimal("0")) >= threshold_amount
        and last_activity.get(account_id, cutoff) <= cutoff
    )


async def _credit_payments_due(session: AsyncSession, within_days: int = 7) -> list[dict]:
    """Кредиты, платёж по которым близко.

    Единственное оповещение здесь с настоящим сроком: остальные говорят о
    тенденции, а это — о дате, которую можно пропустить и заплатить пеню.
    Долг ноль означает, что платить нечего, и напоминание было бы шумом.
    """
    from app.models.credit import CreditTerms
    from app.services.account_service import get_balances_by_account
    from app.services.credit_service import next_payment_date

    today = date.today()
    rows = (
        await session.execute(
            select(CreditTerms, Account.name)
            .join(Account, Account.id == CreditTerms.account_id)
            .where(CreditTerms.payment_day.is_not(None))
        )
    ).all()
    balances = await get_balances_by_account(session)

    due: list[dict] = []
    for terms, account_name in rows:
        debt = max(-balances.get(terms.account_id, Decimal("0")), Decimal("0"))
        if debt <= 0:
            continue
        payment_on = next_payment_date(terms.payment_day, today)
        if payment_on is None:
            continue
        days_left = (payment_on - today).days
        if 0 <= days_left <= within_days:
            due.append({"name": account_name, "days": days_left})
    return due


async def _goals_without_an_account(session: AsyncSession) -> int:
    """Цели, не привязанные к счёту.

    Такая цель считается, но счёт не может показать «отложено»: деньги
    обещаны, а откуда они возьмутся, неизвестно. Тихая половинчатость —
    хуже явной, поэтому о ней говорится вслух.
    """
    from app.models.enums import GoalStatus
    from app.models.goal import Goal

    return int(
        (
            await session.execute(
                select(func.count(Goal.id)).where(
                    Goal.account_id.is_(None), Goal.status == GoalStatus.ACTIVE
                )
            )
        ).scalar_one()
    )


async def _oversold_holdings(session: AsyncSession) -> int:
    """Позиции, где продано больше, чем куплено.

    Не ошибка расчёта, а пропуск в данных: забытая покупка или неверная
    дата. Прибыль по такой позиции завышена, и молчать об этом нельзя.
    """
    from app.models.investment import InvestmentHolding
    from app.services.investment_service import chronological
    from app.services.fifo import replay

    holdings = (
        (
            await session.execute(
                select(InvestmentHolding)
                .options(selectinload(InvestmentHolding.trades))
                .where(InvestmentHolding.is_archived.is_(False))
            )
        )
        .scalars()
        .all()
    )
    return sum(1 for holding in holdings if replay(chronological(list(holding.trades))).oversold > 0)


async def get_financial_alerts(session: AsyncSession) -> AlertsResponse:
    settings = await get_or_create_app_settings(session)
    alerts: list[FinancialAlert] = []

    cash_flow_streak = await _negative_cash_flow_streak(session)
    if cash_flow_streak >= settings.negative_cash_flow_threshold_months:
        alerts.append(
            FinancialAlert(
                key="negative_cash_flow_streak",
                severity="warning",
                params={"months": cash_flow_streak},
            )
        )

    net_worth_summary = await get_net_worth_summary(session, "all")

    net_worth_streak = _net_worth_decline_streak(net_worth_summary)
    if net_worth_streak >= settings.net_worth_decline_threshold_months:
        alerts.append(
            FinancialAlert(
                key="net_worth_decline_streak",
                severity="warning",
                params={"months": net_worth_streak},
            )
        )

    risky_percent = sum(tier.percent for tier in net_worth_summary.risk_levels if tier.risk_level != "low")
    if risky_percent > settings.risky_allocation_threshold_percent:
        alerts.append(
            FinancialAlert(
                key="risky_allocation_exceeded",
                severity="warning",
                params={"percent": round(risky_percent), "threshold": settings.risky_allocation_threshold_percent},
            )
        )

    today = date.today()
    budget_status = await get_budget_status(session, today.year, today.month)
    over_budget_count = sum(1 for item in budget_status.items if item.is_over_budget)
    if over_budget_count > 0:
        alerts.append(
            FinancialAlert(
                key="budget_exceeded",
                severity="warning",
                params={"count": over_budget_count},
            )
        )

    idle_cash_count = await _idle_cash_account_count(
        session, settings.idle_cash_threshold_amount, settings.idle_cash_threshold_days
    )
    if idle_cash_count > 0:
        alerts.append(
            FinancialAlert(
                key="idle_cash",
                severity="warning",
                params={"count": idle_cash_count, "days": settings.idle_cash_threshold_days},
            )
        )

    for credit in await _credit_payments_due(session):
        alerts.append(
            FinancialAlert(
                key="credit_payment_due",
                # Единственное оповещение о дате, а не о тенденции: пропущенный
                # платёж стоит пени сразу, а не через полгода.
                severity="warning",
                params={"name": credit["name"], "days": credit["days"]},
            )
        )

    goals_unlinked = await _goals_without_an_account(session)
    if goals_unlinked > 0:
        alerts.append(
            FinancialAlert(
                key="goal_without_account",
                severity="info",
                params={"count": goals_unlinked},
            )
        )

    oversold = await _oversold_holdings(session)
    if oversold > 0:
        alerts.append(
            FinancialAlert(
                key="investment_oversold",
                severity="warning",
                params={"count": oversold},
            )
        )

    return AlertsResponse(alerts=alerts)
