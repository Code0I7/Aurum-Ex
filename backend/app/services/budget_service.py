"""Monthly category budgets: CRUD for the limits themselves, plus
get_budget_status(), which compares each limit against actual spend for a
given month — the data behind the Budget page's progress bars and the
budget_exceeded proactive alert (services/insights_service.py).

Лимит месяца берётся из двух источников, и между ними действует правило
старшинства: **свой бюджет главнее плана**.

Бюджет и планирование описывали одно и то же разными словами. «По плану 5к
на еду в декабре» и «лимит на еду 5к» — одна и та же цифра, заведённая
дважды, и советы при этом продолжали требовать завести бюджет у категории,
у которой план уже был.

Поэтому категория с планом и без своего бюджета получает строку, выведенную
из плана. Она даже точнее обычного бюджета: у того один потолок на все
месяцы, а плановая сумма считается на каждый месяц отдельно — февраль у
ежедневного плана короче, разовая покупка стоит только в своём месяце.

Заводить бюджет поверх плана не запрещено: свой бюджет просто вытесняет
плановую строку. Отсюда и отсутствие режимов и предупреждений о
столкновении — столкновения нет по построению, есть старшинство.
"""
import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.budget import Budget
from app.models.category import Category
from app.models.enums import CategoryKind, TransactionType
from app.models.transaction import Transaction, TransactionSplit
from app.models.plan import Plan
from app.services.category_tree import load_category_tree
from app.services.plan_service import workdays_by_month, expand_plan
from app.services.transaction_service import counted_only
from app.schemas.budget import BudgetCreate, BudgetStatus, BudgetStatusResponse, BudgetUpdate

_EAGER = (selectinload(Budget.category),)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


async def list_budgets(session: AsyncSession) -> list[Budget]:
    result = await session.execute(select(Budget).options(*_EAGER).join(Category).order_by(Category.sort_order))
    return list(result.scalars().all())


async def create_budget(session: AsyncSession, payload: BudgetCreate) -> Budget:
    category = await session.get(Category, payload.category_id)
    if category is None:
        raise HTTPException(status_code=400, detail="Category not found")
    if category.kind != CategoryKind.EXPENSE:
        raise HTTPException(status_code=400, detail="Budgets can only be set on expense categories")

    existing = await session.execute(select(Budget).where(Budget.category_id == payload.category_id))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail=f"'{category.name}' already has a budget")

    budget = Budget(category_id=payload.category_id, monthly_limit=payload.monthly_limit)
    session.add(budget)
    await session.commit()
    refreshed = await session.execute(select(Budget).options(*_EAGER).where(Budget.id == budget.id))
    return refreshed.scalar_one()


async def update_budget(session: AsyncSession, budget_id: int, payload: BudgetUpdate) -> Budget:
    budget = await session.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status_code=404, detail="Budget not found")
    budget.monthly_limit = payload.monthly_limit
    await session.commit()
    refreshed = await session.execute(select(Budget).options(*_EAGER).where(Budget.id == budget_id))
    return refreshed.scalar_one()


async def delete_budget(session: AsyncSession, budget_id: int) -> None:
    budget = await session.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status_code=404, detail="Budget not found")
    await session.delete(budget)
    await session.commit()


@dataclass
class _Line:
    """Одна строка бюджета: откуда лимит и чей он."""

    category: Category
    monthly_limit: Decimal
    # None — строка выведена из плана, своей записи в бюджетах нет.
    budget_id: int | None


async def _plan_lines(
    session: AsyncSession, year: int, month: int, taken: set[int]
) -> list[_Line]:
    """Строки, выведенные из планов на этот месяц.

    Берутся только расходные категории: план на зарплату — это ожидание
    дохода, а не потолок траты, и полоса «истрачено 96%» для него означала
    бы обратное тому, что происходит.

    Категории, у которых есть свой бюджет, пропускаются: свой главнее.

    Несколько планов на одну категорию складываются — «связь 700» и
    «интернет 500» это две записи, а строка одна. Так же они складываются и
    в самом «Планировании».
    """
    plans = (
        (
            await session.execute(
                select(Plan).where(Plan.category_id.is_not(None), Plan.category_id.not_in(taken or {0}))
            )
        )
        .scalars()
        .all()
    )
    if not plans:
        return []

    workdays = (await workdays_by_month(session, year)).get((year, month))
    limits: dict[int, Decimal] = defaultdict(Decimal)
    for plan in plans:
        amount = expand_plan(plan, year, month, workdays)
        if amount:
            limits[plan.category_id] += amount
    if not limits:
        return []

    categories = (
        (await session.execute(select(Category).where(Category.id.in_(limits)))).scalars().all()
    )
    return [
        _Line(category=category, monthly_limit=limits[category.id], budget_id=None)
        for category in categories
        if category.kind is CategoryKind.EXPENSE
    ]


async def get_budget_status(session: AsyncSession, year: int, month: int) -> BudgetStatusResponse:
    start, end = _month_bounds(year, month)

    budgets = await list_budgets(session)
    lines = [
        _Line(category=budget.category, monthly_limit=budget.monthly_limit, budget_id=budget.id)
        for budget in budgets
    ]
    lines.extend(await _plan_lines(session, year, month, {budget.category_id for budget in budgets}))
    if not lines:
        return BudgetStatusResponse(year=year, month=month, items=[])

    # A budget on a top-level category covers its subcategories too — the
    # same rollup the Dashboard breakdown and the category report already do
    # (coalesce(parent_id, id) in dashboard_service/reports_service).
    # Counting only exact category_id matches meant a month could read as 900
    # spent on the Dashboard and 0 against its own budget. A subcategory that
    # has a budget of its own still tracks its own spending: both bars move,
    # each against its own limit.
    # Ветка берётся целиком, на любую глубину: бюджет на «Продуктах» обязан
    # видеть сыр, лежащий двумя уровнями ниже, иначе месяц читался бы как
    # 900 потрачено на дашборде и 0 против собственного бюджета.
    tree = await load_category_tree(session)
    budget_category_ids = [line.category.id for line in lines]
    children_by_parent: dict[int, list[int]] = defaultdict(list)
    for parent_id in budget_category_ids:
        children_by_parent[parent_id] = tree.descendants_of(parent_id)

    counted_ids = set(budget_category_ids).union(
        child_id for children in children_by_parent.values() for child_id in children
    )
    # A split transaction has category_id=NULL on its own row — its spend
    # lives on its split lines instead (see category_rollup.py), so a plain
    # sum on Transaction.category_id alone would silently under-count a
    # budget funded partly by split purchases.
    plain_stmt = (
        select(Transaction.category_id, func.coalesce(func.sum(Transaction.amount), 0))
        .where(
            Transaction.category_id.in_(counted_ids),
            Transaction.type == TransactionType.EXPENSE,
            counted_only(),
            Transaction.date >= start,
            Transaction.date <= end,
        )
        .group_by(Transaction.category_id)
    )
    split_stmt = (
        select(TransactionSplit.category_id, func.coalesce(func.sum(TransactionSplit.amount), 0))
        .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
        .where(
            TransactionSplit.category_id.in_(counted_ids),
            Transaction.type == TransactionType.EXPENSE,
            counted_only(),
            Transaction.date >= start,
            Transaction.date <= end,
        )
        .group_by(TransactionSplit.category_id)
    )
    spent_by_category: dict[int, Decimal] = defaultdict(Decimal)
    for category_id, amount in (await session.execute(plain_stmt)).all():
        spent_by_category[category_id] += amount
    for category_id, amount in (await session.execute(split_stmt)).all():
        spent_by_category[category_id] += amount

    items = []
    for line in lines:
        spent = spent_by_category.get(line.category.id, Decimal("0")) + sum(
            (spent_by_category.get(child_id, Decimal("0")) for child_id in children_by_parent[line.category.id]),
            Decimal("0"),
        )
        percent = float(spent / line.monthly_limit * 100) if line.monthly_limit else 0.0
        items.append(
            BudgetStatus(
                budget_id=line.budget_id,
                source="budget" if line.budget_id is not None else "plan",
                category_id=line.category.id,
                category_name=line.category.name,
                category_color=line.category.color,
                category_icon=line.category.icon,
                monthly_limit=line.monthly_limit,
                spent=spent,
                remaining=line.monthly_limit - spent,
                percent=percent,
                is_over_budget=spent > line.monthly_limit,
            )
        )

    return BudgetStatusResponse(year=year, month=month, items=items)
