"""Планирование: план на год против факта.

Отдельно от бюджетов (`/budgets`), хотя обе вещи про «сколько собирались
потратить». Бюджет — потолок на месяц, который предупреждает; план —
ожидание на годы вперёд, из которого складывается картина года. Свести их в
один ресурс значило бы заставить выбирать между предупреждением и прогнозом.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.plan import (
    MonthCellOut,
    PlanCreate,
    PlanOverviewOut,
    PlanRead,
    PlanRowOut,
    PlanUpdate,
    WatchlistOut,
    WatchRowOut,
)
from app.services.plan_service import (
    create_plan,
    delete_plan,
    get_plan_overview,
    get_watchlist_overview,
    list_plans,
    update_plan,
)

router = APIRouter(prefix="/plans", tags=["plans"])


def _cell(cell) -> MonthCellOut:
    return MonthCellOut(
        month=cell.month,
        planned=cell.planned,
        actual=cell.actual,
        deviation=cell.deviation,
    )


@router.get("", response_model=list[PlanRead])
async def read_plans(session: AsyncSession = Depends(get_session)) -> list[PlanRead]:
    plans = await list_plans(session)
    return [
        PlanRead(
            **{field: getattr(plan, field) for field in PlanRead.model_fields if field != "category_name"},
            category_name=plan.category.name if plan.category else None,
        )
        for plan in plans
    ]


@router.get("/overview", response_model=PlanOverviewOut)
async def read_plan_overview(
    year: int = Query(..., ge=1970, le=2200), session: AsyncSession = Depends(get_session)
) -> PlanOverviewOut:
    """Таблица года. Строится по требованию, а не хранится: план меняется
    правкой одной записи, и пересчитанная таблица должна отражать это сразу.
    """
    overview = await get_plan_overview(session, year)
    return PlanOverviewOut(
        year=overview["year"],
        rows=[
            PlanRowOut(
                category_id=row.category_id,
                name=row.name,
                kind=row.kind,
                months=[_cell(cell) for cell in row.months],
                planned_total=row.planned_total,
                actual_total=row.actual_total,
            )
            for row in overview["rows"]
        ],
        income_totals=[_cell(cell) for cell in overview["income_totals"]],
        expense_totals=[_cell(cell) for cell in overview["expense_totals"]],
        free_totals=[_cell(cell) for cell in overview["free_totals"]],
    )


@router.get("/watchlist", response_model=WatchlistOut)
async def read_watchlist(
    year: int = Query(..., ge=1970, le=2200), session: AsyncSession = Depends(get_session)
) -> WatchlistOut:
    """Отмеченные категории по месяцам. Что отмечено — признак на самой
    категории, поэтому список меняется через /categories, а не отдельным
    ресурсом: наблюдение — свойство категории, а не самостоятельная вещь.
    """
    overview = await get_watchlist_overview(session, year)
    return WatchlistOut(
        year=overview["year"],
        rows=[
            WatchRowOut(
                category_id=row.category_id,
                name=row.name,
                path=row.path,
                kind=row.kind,
                months=row.months,
                total=row.total,
                previous_total=row.previous_total,
            )
            for row in overview["rows"]
        ],
    )


@router.post("", response_model=PlanRead, status_code=201)
async def create_plan_route(payload: PlanCreate, session: AsyncSession = Depends(get_session)) -> PlanRead:
    plan = await create_plan(session, payload)
    return PlanRead.model_validate(plan)


@router.patch("/{plan_id}", response_model=PlanRead)
async def update_plan_route(
    plan_id: int, payload: PlanUpdate, session: AsyncSession = Depends(get_session)
) -> PlanRead:
    plan = await update_plan(session, plan_id, payload)
    return PlanRead.model_validate(plan)


@router.delete("/{plan_id}", status_code=204)
async def delete_plan_route(plan_id: int, session: AsyncSession = Depends(get_session)) -> None:
    """Удаляет план целиком. Чтобы прекратить его с определённого месяца, а
    не стереть из истории, ставят `valid_to`."""
    await delete_plan(session, plan_id)
