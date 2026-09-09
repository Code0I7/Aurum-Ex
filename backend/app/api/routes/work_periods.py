"""Отработанные часы и дни по месяцам.

Вводятся руками, и производственного календаря здесь нет намеренно: график
у людей разный. Сутки через двое, вахта, четыре дня в неделю — календарные
«пн–пт» неверны для всех них, а введённое человеком число верно всегда.

Часы нужны для стоимости часа («эта покупка стоила мне полтора дня работы»),
дни — для планов вида «столовая 300 ₽ в рабочий день».
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.work_period import WorkPeriod
from app.services.hourly_service import get_hourly_rates

router = APIRouter(prefix="/work-periods", tags=["work-periods"])


class WorkPeriodWrite(BaseModel):
    year: int = Field(ge=1970, le=2200)
    month: int = Field(ge=1, le=12)
    # Дробные часы — обычное дело: 164,5 за месяц с половиной смены.
    hours: Decimal = Field(default=Decimal("0"), ge=0, le=744)
    # Дни необязательны: часы нужны почти всем, дни — только тем, у кого
    # есть план «в рабочий день».
    workdays: int | None = Field(default=None, ge=0, le=31)
    participant_id: int | None = None


class WorkPeriodRead(WorkPeriodWrite):
    id: int

    model_config = {"from_attributes": True}


@router.get("", response_model=list[WorkPeriodRead])
async def read_work_periods(
    year: int | None = Query(default=None, ge=1970, le=2200),
    session: AsyncSession = Depends(get_session),
) -> list[WorkPeriodRead]:
    stmt = select(WorkPeriod).order_by(WorkPeriod.year, WorkPeriod.month)
    if year is not None:
        stmt = stmt.where(WorkPeriod.year == year)
    return [WorkPeriodRead.model_validate(row) for row in (await session.execute(stmt)).scalars().all()]


@router.put("", response_model=WorkPeriodRead)
async def save_work_period(
    payload: WorkPeriodWrite, session: AsyncSession = Depends(get_session)
) -> WorkPeriodRead:
    """Создаёт или обновляет запись месяца.

    PUT, а не POST: у месяца либо есть отработанное время, либо нет —
    второй записи за тот же месяц не бывает, и уникальный индекс в базе это
    подтверждает. Два эндпоинта заставили бы интерфейс сначала выяснять,
    заводил ли пользователь этот месяц раньше.
    """
    existing = (
        await session.execute(
            select(WorkPeriod).where(
                WorkPeriod.year == payload.year,
                WorkPeriod.month == payload.month,
                WorkPeriod.participant_id.is_(payload.participant_id)
                if payload.participant_id is None
                else WorkPeriod.participant_id == payload.participant_id,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = WorkPeriod(**payload.model_dump())
        session.add(existing)
    else:
        for field_name, value in payload.model_dump().items():
            setattr(existing, field_name, value)

    await session.commit()
    await session.refresh(existing)
    return WorkPeriodRead.model_validate(existing)


@router.delete("/{period_id}", status_code=204)
async def delete_work_period(period_id: int, session: AsyncSession = Depends(get_session)) -> None:
    period = await session.get(WorkPeriod, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Work period not found")
    await session.delete(period)
    await session.commit()


class HourlyRates(BaseModel):
    """Ставка за час по месяцам и в среднем.

    Ставка месяца — это скользящее окно в три месяца, заканчивающееся им
    самим: одного месяца мало, потому что аванс и зарплата разъезжаются, а
    календарный год смазывает рост заработка и упирается в январь, где
    окно состоит из одного дня (см. services/hourly_service.py).
    """

    # Ключ — «год-месяц» строкой: интерфейс отрезает его от даты операции
    # напрямую, без разбора даты и без часовых поясов.
    months: dict[str, str]
    # None, когда часов не введено вовсе: выдумывать ставку хуже, чем
    # промолчать.
    overall: str | None


@router.get("/hourly-rates", response_model=HourlyRates)
async def read_hourly_rates(session: AsyncSession = Depends(get_session)) -> HourlyRates:
    rates = await get_hourly_rates(session)
    return HourlyRates(months=rates["months"], overall=rates["overall"])
