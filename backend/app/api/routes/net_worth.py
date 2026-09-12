from datetime import date as date_

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.net_worth import NetWorthSummary
from app.services.net_worth_service import RANGE_DAYS, get_net_worth_summary

router = APIRouter(prefix="/net-worth", tags=["net-worth"])

# «custom» — не длина, а признак того, что период задан датами. Он
# входит в набор, потому что интерфейс присылает его вместе с ними и
# получает обратно, чтобы подсветить нужную кнопку.
_VALID_RANGES = sorted(set(RANGE_DAYS) | {"all", "custom"})
_RANGE_PATTERN = f"^({'|'.join(_VALID_RANGES)})$"


@router.get("/summary", response_model=NetWorthSummary)
async def read_net_worth_summary(
    range: str = Query(default="30d", pattern=_RANGE_PATTERN),
    start_date: date_ | None = Query(default=None),
    end_date: date_ | None = Query(default=None),
    # Валюта, в которой считать. Не указана — своя. Капитал не
    # переводится, поэтому это выбор «что смотрю», а не «в чём показать».
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    session: AsyncSession = Depends(get_session),
) -> NetWorthSummary:
    """Готовый период или свой.

    Свой задаётся датами и перекрывает `range`; сам `range` при этом
    остаётся в ответе как «custom» — интерфейсу нужно знать, что выбрано,
    чтобы не подсвечивать чужую кнопку.
    """
    return await get_net_worth_summary(session, range, start_date, end_date, currency)
