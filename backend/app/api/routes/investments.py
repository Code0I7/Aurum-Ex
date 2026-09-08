"""Инвестиции: портфели, позиции, сделки.

Один раздел на все семейства активов. Вкладка, на которой актив
показывается, — фильтр по виду (`kind`), а не отдельный ресурс: партии и
списание при продаже устроены одинаково для акции и для монеты, и разводить
их по разным адресам значило бы обещать разницу, которой нет.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.investment import (
    HoldingCreate,
    HoldingDetail,
    HoldingRead,
    HoldingUpdate,
    PortfolioCreate,
    PortfolioRead,
    PortfolioUpdate,
    TradeCreate,
    TradeRead,
    TradeUpdate,
)
from app.services.investment_service import (
    add_trade,
    create_holding,
    create_portfolio,
    delete_holding,
    delete_portfolio,
    delete_trade,
    get_holding_detail,
    list_holdings,
    list_portfolios,
    list_trades,
    update_holding,
    update_portfolio,
    update_trade,
)

router = APIRouter(prefix="/investments", tags=["investments"])


# --- Портфели ---


@router.get("/portfolios", response_model=list[PortfolioRead])
async def read_portfolios(
    include_archived: bool = False, session: AsyncSession = Depends(get_session)
) -> list[PortfolioRead]:
    return await list_portfolios(session, include_archived)


@router.post("/portfolios", response_model=PortfolioRead, status_code=201)
async def create_portfolio_route(
    payload: PortfolioCreate, session: AsyncSession = Depends(get_session)
) -> PortfolioRead:
    return await create_portfolio(session, payload)


@router.patch("/portfolios/{portfolio_id}", response_model=PortfolioRead)
async def update_portfolio_route(
    portfolio_id: int, payload: PortfolioUpdate, session: AsyncSession = Depends(get_session)
) -> PortfolioRead:
    return await update_portfolio(session, portfolio_id, payload)


@router.delete("/portfolios/{portfolio_id}", status_code=204)
async def delete_portfolio_route(portfolio_id: int, session: AsyncSession = Depends(get_session)) -> None:
    await delete_portfolio(session, portfolio_id)


# --- Позиции ---


@router.get("/holdings", response_model=list[HoldingRead])
async def read_holdings(
    portfolio_id: int | None = Query(default=None),
    include_archived: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[HoldingRead]:
    return await list_holdings(session, portfolio_id, include_archived)


@router.get("/holdings/{holding_id}", response_model=HoldingDetail)
async def read_holding(holding_id: int, session: AsyncSession = Depends(get_session)) -> HoldingDetail:
    """Позиция с открытыми партиями и историей фиксаций.

    Разнесение продаж по партиям показывается наружу намеренно: «продали то,
    что купили в мае 2022-го» — ответ, который средневзвешенная дать не
    могла в принципе, и ради которого метод и менялся.
    """
    return await get_holding_detail(session, holding_id)


@router.post("/holdings", response_model=HoldingRead, status_code=201)
async def create_holding_route(
    payload: HoldingCreate, session: AsyncSession = Depends(get_session)
) -> HoldingRead:
    return await create_holding(session, payload)


@router.patch("/holdings/{holding_id}", response_model=HoldingRead)
async def update_holding_route(
    holding_id: int, payload: HoldingUpdate, session: AsyncSession = Depends(get_session)
) -> HoldingRead:
    return await update_holding(session, holding_id, payload)


@router.delete("/holdings/{holding_id}", status_code=204)
async def delete_holding_route(holding_id: int, session: AsyncSession = Depends(get_session)) -> None:
    """Удаляет позицию вместе со сделками. Для закрытой позиции обычный путь
    — архивирование: зафиксированная прибыль остаётся частью истории."""
    await delete_holding(session, holding_id)


# --- Сделки ---


@router.get("/holdings/{holding_id}/trades", response_model=list[TradeRead])
async def read_trades(holding_id: int, session: AsyncSession = Depends(get_session)) -> list[TradeRead]:
    return [TradeRead.model_validate(trade) for trade in await list_trades(session, holding_id)]


@router.post("/holdings/{holding_id}/trades", response_model=HoldingRead, status_code=201)
async def add_trade_route(
    holding_id: int, payload: TradeCreate, session: AsyncSession = Depends(get_session)
) -> HoldingRead:
    """Добавляет сделку и возвращает пересчитанную позицию.

    Возвращается позиция, а не сама сделка: после покупки человека
    интересует, что стало с позицией, а не идентификатор записи.
    """
    return await add_trade(session, holding_id, payload)


@router.patch("/trades/{trade_id}", response_model=HoldingRead)
async def update_trade_route(
    trade_id: int, payload: TradeUpdate, session: AsyncSession = Depends(get_session)
) -> HoldingRead:
    return await update_trade(session, trade_id, payload)


@router.delete("/trades/{trade_id}", response_model=HoldingRead)
async def delete_trade_route(trade_id: int, session: AsyncSession = Depends(get_session)) -> HoldingRead:
    return await delete_trade(session, trade_id)
