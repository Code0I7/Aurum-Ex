"""Инвестиции: портфели, позиции, сделки.

Один движок на все семейства активов — акции, облигации, фонды, крипта,
металлы. Партии, стоимость владения и списание при продаже — одинаковая
арифметика для акции и для монеты, и держать два параллельных модуля
значило бы чинить каждую ошибку дважды. Вкладка, на которой актив
показывается, — это фильтр, а не отдельная система.

Списание по FIFO (см. services/fifo.py), а не по средневзвешенной, которой
считал прежний крипто-модуль. Один метод на всё приложение предотвращает
худшее: две соседние вкладки, расходящиеся в оценке одинаковых операций.

Количество и стоимость владения нигде не хранятся: они пересчитываются из
журнала сделок при каждом чтении. Хранимый итог — второй источник истины, и
он расходится с журналом при первой же правке сделки.
"""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.investment import InvestmentHolding, InvestmentPortfolio, InvestmentTrade
from app.schemas.investment import (
    DisposalLot,
    DisposalRead,
    HoldingCreate,
    HoldingDetail,
    HoldingRead,
    HoldingUpdate,
    PortfolioCreate,
    PortfolioRead,
    PortfolioUpdate,
    TradeCreate,
    TradeUpdate,
)
from app.services.currency_service import quantize_money
from app.services.fifo import Position, replay


def chronological(trades: list[InvestmentTrade]) -> list[InvestmentTrade]:
    """Порядок прогона: дата, затем порядок внутри дня, затем идентификатор.

    Тай-брейк обязателен. Две сделки одной датой не должны меняться местами
    между двумя загрузками страницы — иначе зафиксированная прибыль менялась
    бы при обновлении, а это худшее, что может делать приложение про деньги.
    """
    return sorted(trades, key=lambda trade: (trade.trade_date, trade.day_order, trade.id))


def _position_of(holding: InvestmentHolding) -> Position:
    return replay(chronological(list(holding.trades)))


def _to_read(holding: InvestmentHolding, position: Position | None = None) -> HoldingRead:
    position = position or _position_of(holding)
    price = holding.last_price
    # Стоимость None, а не ноль, когда цена неизвестна: ноль означал бы, что
    # актив обесценился, а он просто не переоценён.
    value = price * position.quantity if price is not None else None
    unrealised = value - position.cost_basis if value is not None else None
    unrealised_percent = (
        float(round(unrealised / position.cost_basis * 100, 2))
        if unrealised is not None and position.cost_basis > 0
        else None
    )
    return HoldingRead(
        id=holding.id,
        portfolio_id=holding.portfolio_id,
        name=holding.name,
        ticker=holding.ticker,
        kind=holding.kind,
        currency=holding.currency,
        external_id=holding.external_id,
        risk_level=holding.risk_level,
        notes=holding.notes,
        is_archived=holding.is_archived,
        last_price=price,
        last_price_at=holding.last_price_at,
        quantity=position.quantity,
        cost_basis=quantize_money(position.cost_basis),
        invested=quantize_money(position.invested),
        average_cost=position.average_cost,
        value=quantize_money(value) if value is not None else None,
        unrealised=quantize_money(unrealised) if unrealised is not None else None,
        unrealised_percent=unrealised_percent,
        realised=quantize_money(position.realised),
        oversold=position.oversold,
        trades=len(holding.trades),
    )


async def _holdings_query(session: AsyncSession, *, portfolio_id: int | None, include_archived: bool):
    stmt = (
        select(InvestmentHolding)
        .options(selectinload(InvestmentHolding.trades))
        .order_by(InvestmentHolding.name)
    )
    if portfolio_id is not None:
        stmt = stmt.where(InvestmentHolding.portfolio_id == portfolio_id)
    if not include_archived:
        stmt = stmt.where(InvestmentHolding.is_archived.is_(False))
    return (await session.execute(stmt)).scalars().all()


async def list_holdings(
    session: AsyncSession, portfolio_id: int | None = None, include_archived: bool = False
) -> list[HoldingRead]:
    holdings = await _holdings_query(session, portfolio_id=portfolio_id, include_archived=include_archived)
    reads = [_to_read(holding) for holding in holdings]
    # Сначала то, во что вложено больше всего денег, а не то, что дороже
    # стоит сейчас: список отвечает на вопрос «где мои деньги», и позиция,
    # выросшая втрое, не важнее той, в которую вложено втрое больше.
    return sorted(reads, key=lambda item: -item.cost_basis)


async def get_holding_detail(session: AsyncSession, holding_id: int) -> HoldingDetail:
    holding = await session.get(
        InvestmentHolding, holding_id, options=[selectinload(InvestmentHolding.trades)]
    )
    if holding is None:
        raise HTTPException(status_code=404, detail="Holding not found")

    trades = chronological(list(holding.trades))
    position = replay(trades)
    base = _to_read(holding, position)

    # Продажи сопоставляются со сделками по порядку: движок складывает их в
    # том же порядке, в каком получил журнал, поэтому n-я продажа в списке
    # соответствует n-й продаже в журнале.
    sell_trades = [trade for trade in trades if getattr(trade.side, "value", trade.side) == "sell"]
    disposals = [
        DisposalRead(
            trade_id=trade.id,
            trade_date=trade.trade_date,
            quantity=disposal.quantity,
            proceeds=quantize_money(disposal.proceeds),
            cost=quantize_money(disposal.cost),
            realised=quantize_money(disposal.realised),
            lots=[
                DisposalLot(quantity=qty, cost_per_unit=cost, acquired_on=when)
                for qty, cost, when in disposal.lots
            ],
        )
        for trade, disposal in zip(sell_trades, position.disposals)
    ]

    return HoldingDetail(
        **base.model_dump(),
        open_lots=[
            DisposalLot(quantity=lot.quantity, cost_per_unit=lot.cost_per_unit, acquired_on=lot.acquired_on)
            for lot in position.lots
        ],
        disposals=disposals,
    )


async def create_holding(session: AsyncSession, payload: HoldingCreate) -> HoldingRead:
    if await session.get(InvestmentPortfolio, payload.portfolio_id) is None:
        raise HTTPException(status_code=400, detail="Portfolio not found")
    holding = InvestmentHolding(**payload.model_dump())
    session.add(holding)
    await session.commit()
    await session.refresh(holding, ["trades"])
    return _to_read(holding)


async def update_holding(session: AsyncSession, holding_id: int, payload: HoldingUpdate) -> HoldingRead:
    holding = await session.get(
        InvestmentHolding, holding_id, options=[selectinload(InvestmentHolding.trades)]
    )
    if holding is None:
        raise HTTPException(status_code=404, detail="Holding not found")
    updates = payload.model_dump(exclude_unset=True)
    if "portfolio_id" in updates and await session.get(InvestmentPortfolio, updates["portfolio_id"]) is None:
        raise HTTPException(status_code=400, detail="Portfolio not found")
    if "last_price" in updates:
        # Ручная переоценка ставит отметку времени сама: цена без даты не
        # даёт понять, вчерашняя она или двухлетней давности.
        from datetime import datetime, timezone

        holding.last_price_at = datetime.now(timezone.utc)
    for field, value in updates.items():
        setattr(holding, field, value)
    await session.commit()
    await session.refresh(holding, ["trades"])
    return _to_read(holding)


async def delete_holding(session: AsyncSession, holding_id: int) -> None:
    """Удаляет позицию вместе со всеми её сделками.

    Архивирование — обычный путь для закрытой позиции: зафиксированная по
    ней прибыль остаётся частью истории, а удаление стирает и её.
    """
    holding = await session.get(InvestmentHolding, holding_id)
    if holding is None:
        raise HTTPException(status_code=404, detail="Holding not found")
    await session.delete(holding)
    await session.commit()


async def _next_day_order(session: AsyncSession, holding_id: int, trade_date) -> int:
    stmt = select(func.coalesce(func.max(InvestmentTrade.day_order), -1)).where(
        InvestmentTrade.holding_id == holding_id, InvestmentTrade.trade_date == trade_date
    )
    return int((await session.execute(stmt)).scalar_one()) + 1


async def add_trade(session: AsyncSession, holding_id: int, payload: TradeCreate) -> HoldingRead:
    holding = await session.get(
        InvestmentHolding, holding_id, options=[selectinload(InvestmentHolding.trades)]
    )
    if holding is None:
        raise HTTPException(status_code=404, detail="Holding not found")

    trade = InvestmentTrade(holding_id=holding_id, **payload.model_dump())
    # Порядок внутри дня проставляется по времени ввода, как у операций по
    # счёту: человеку не за чем его набирать, а без него две сделки одной
    # датой раскладываются произвольно и прибыль скачет.
    trade.day_order = await _next_day_order(session, holding_id, payload.trade_date)
    session.add(trade)
    await session.commit()
    await session.refresh(holding, ["trades"])
    return _to_read(holding)


async def update_trade(session: AsyncSession, trade_id: int, payload: TradeUpdate) -> HoldingRead:
    trade = await session.get(InvestmentTrade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(trade, field, value)
    await session.commit()
    holding = await session.get(
        InvestmentHolding, trade.holding_id, options=[selectinload(InvestmentHolding.trades)]
    )
    return _to_read(holding)


async def delete_trade(session: AsyncSession, trade_id: int) -> HoldingRead:
    trade = await session.get(InvestmentTrade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    holding_id = trade.holding_id
    await session.delete(trade)
    await session.commit()
    holding = await session.get(
        InvestmentHolding, holding_id, options=[selectinload(InvestmentHolding.trades)]
    )
    return _to_read(holding)


async def list_trades(session: AsyncSession, holding_id: int) -> list[InvestmentTrade]:
    trades = (
        await session.execute(select(InvestmentTrade).where(InvestmentTrade.holding_id == holding_id))
    ).scalars().all()
    # Новые сверху: журнал читают с последней сделки, а не с первой.
    return list(reversed(chronological(list(trades))))


async def list_portfolios(session: AsyncSession, include_archived: bool = False) -> list[PortfolioRead]:
    stmt = select(InvestmentPortfolio).order_by(InvestmentPortfolio.name)
    if not include_archived:
        stmt = stmt.where(InvestmentPortfolio.is_archived.is_(False))
    portfolios = (await session.execute(stmt)).scalars().all()

    holdings = await _holdings_query(session, portfolio_id=None, include_archived=False)
    reads: list[PortfolioRead] = []
    for portfolio in portfolios:
        own = [holding for holding in holdings if holding.portfolio_id == portfolio.id]
        positions = [_to_read(holding) for holding in own]
        reads.append(
            PortfolioRead(
                id=portfolio.id,
                name=portfolio.name,
                color=portfolio.color,
                is_archived=portfolio.is_archived,
                holdings=len(own),
                value=quantize_money(
                    sum((item.value or Decimal("0") for item in positions), Decimal("0"))
                ),
                cost_basis=quantize_money(sum((item.cost_basis for item in positions), Decimal("0"))),
            )
        )
    return reads


async def create_portfolio(session: AsyncSession, payload: PortfolioCreate) -> PortfolioRead:
    portfolio = InvestmentPortfolio(**payload.model_dump())
    session.add(portfolio)
    await session.commit()
    await session.refresh(portfolio)
    return PortfolioRead(
        id=portfolio.id, name=portfolio.name, color=portfolio.color, is_archived=portfolio.is_archived
    )


async def update_portfolio(
    session: AsyncSession, portfolio_id: int, payload: PortfolioUpdate
) -> PortfolioRead:
    portfolio = await session.get(InvestmentPortfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(portfolio, field, value)
    await session.commit()
    return PortfolioRead(
        id=portfolio.id, name=portfolio.name, color=portfolio.color, is_archived=portfolio.is_archived
    )


async def delete_portfolio(session: AsyncSession, portfolio_id: int) -> None:
    """Удаляет портфель. Позиции внутри уходят вместе с ним (CASCADE),
    поэтому непустой портфель удалить нельзя — это стёрло бы историю сделок
    заодно."""
    portfolio = await session.get(InvestmentPortfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    has_holdings = (
        await session.execute(
            select(InvestmentHolding.id).where(InvestmentHolding.portfolio_id == portfolio_id).limit(1)
        )
    ).first()
    if has_holdings is not None:
        raise HTTPException(
            status_code=400, detail="Move or delete the holdings inside this portfolio first"
        )
    await session.delete(portfolio)
    await session.commit()
