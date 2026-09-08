from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard_service import get_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def read_dashboard_summary(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    range: Literal["month", "year", "all"] = Query(default="month"),
    session: AsyncSession = Depends(get_session),
) -> DashboardSummary:
    """Сводка за месяц, год или всё время.

    По умолчанию месяц — эндпоинт не должен молча менять смысл ответа для
    того, кто просто передал год и месяц. Какой период показывать при
    открытии, решает интерфейс, и он выбирает «за всё время».
    """
    return await get_dashboard_summary(session, year, month, range)
