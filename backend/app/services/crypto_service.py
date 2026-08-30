"""Crypto price sync: CoinGecko Demo API calls, written into the *existing*
Asset/AssetValuation engine (see models/asset.py) rather than a parallel
value-tracking system. A CryptoHolding only ever records identity (which
coin) and quantity (how much) — the actual value is an ordinary
AssetValuation row, so Net Worth, reports, and everything else that already
walks Asset rows needs zero changes to treat a crypto holding like any
other manually tracked asset.

Refreshes are deliberately never automatic in the background — same
reasoning as recurring transactions (see services/recurring_service.py):
there's no scheduler/worker in this stack, and a rate-limited free API key
makes "poll constantly" actively counterproductive anyway. Two triggers
only: the "Refresh prices" button (force=True) and a lazy once-a-day check
that piggybacks on GET /crypto/holdings (force=False) — see
routes/crypto.py.
"""
from datetime import date as date_
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models.asset import Asset, AssetValuation
from app.models.crypto import CryptoHolding, CryptoSyncState
from app.models.enums import AssetClass, CapitalRole, RiskLevel
from app.schemas.crypto import CryptoHoldingCreate, CryptoHoldingRead, CryptoSearchResult, CryptoSyncResult
from app.services.settings_service import get_or_create_app_settings

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
# CoinGecko's own Demo-tier data only refreshes every 60s server-side
# (see docs.coingecko.com/reference/simple-price) — polling more often than
# once a day here buys nothing and only spends rate-limit budget for no
# reason (see module docstring on why there's no background poller at all).
AUTO_REFRESH_INTERVAL = timedelta(hours=24)

_EAGER = (selectinload(CryptoHolding.asset).selectinload(Asset.valuations),)


def _require_api_key() -> str:
    api_key = get_settings().coingecko_api_key
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=(
                "CoinGecko API key not configured — set AURUM_COINGECKO_API_KEY in .env "
                "(free Demo key, no card required: coingecko.com/en/api/pricing)."
            ),
        )
    return api_key


async def _fetch_prices_batch(coingecko_ids: list[str], vs_currency: str) -> dict[str, Decimal]:
    """One CoinGecko call for every tracked coin at once (up to 515 ids per
    call) — never one call per coin, that's what would actually burn
    through a free-tier rate limit."""
    if not coingecko_ids:
        return {}
    api_key = _require_api_key()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{COINGECKO_BASE_URL}/simple/price",
            params={"ids": ",".join(coingecko_ids), "vs_currencies": vs_currency},
            headers={"x-cg-demo-api-key": api_key},
        )
        response.raise_for_status()
        data = response.json()
    prices: dict[str, Decimal] = {}
    for coin_id, values in data.items():
        price = values.get(vs_currency)
        if price is not None:
            prices[coin_id] = Decimal(str(price))
    return prices


async def search_coins(query: str) -> list[CryptoSearchResult]:
    """Backs the "add a coin" picker — the whole reason a user can find the
    right coingecko_id without knowing it by heart, same as typing a name
    into CoinMarketCap's own search box."""
    api_key = _require_api_key()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{COINGECKO_BASE_URL}/search",
            params={"query": query},
            headers={"x-cg-demo-api-key": api_key},
        )
        response.raise_for_status()
        data = response.json()
    return [
        CryptoSearchResult(
            coingecko_id=coin["id"],
            symbol=str(coin["symbol"]).upper(),
            name=coin["name"],
            thumb_url=coin.get("thumb"),
        )
        for coin in data.get("coins", [])[:20]
    ]


def _to_read(holding: CryptoHolding) -> CryptoHoldingRead:
    latest = holding.asset.valuations[-1] if holding.asset.valuations else None
    value = latest.value if latest else None
    unit_price = (value / holding.quantity) if value is not None and holding.quantity else None
    return CryptoHoldingRead(
        asset_id=holding.asset_id,
        coingecko_id=holding.coingecko_id,
        symbol=holding.symbol,
        name=holding.name,
        thumb_url=holding.thumb_url,
        quantity=holding.quantity,
        value=value,
        unit_price=unit_price,
        as_of_date=latest.as_of_date.isoformat() if latest else None,
    )


async def list_holdings(session: AsyncSession) -> list[CryptoHolding]:
    # populate_existing=True: _upsert_valuation() below writes AssetValuation
    # rows via a raw Core statement, which the ORM's identity map doesn't
    # know happened. Without this, a session that already loaded a holding's
    # valuations once (list_holdings gets called both before and after a
    # refresh's writes) would keep serving the pre-refresh value here.
    result = await session.execute(
        select(CryptoHolding).options(*_EAGER).order_by(CryptoHolding.name).execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def get_or_create_sync_state(session: AsyncSession) -> CryptoSyncState:
    state = await session.get(CryptoSyncState, 1)
    if state is None:
        state = CryptoSyncState(id=1, last_synced_at=None)
        session.add(state)
        await session.commit()
        await session.refresh(state)
    return state


async def _upsert_valuation(session: AsyncSession, asset_id: int, value: Decimal, as_of_date: date_) -> None:
    """Same upsert-by-date pattern as routes/assets.py's POST
    /assets/{id}/valuations — re-syncing the same day updates that day's
    value instead of erroring."""
    upsert_stmt = (
        pg_insert(AssetValuation)
        .values(asset_id=asset_id, value=value, as_of_date=as_of_date)
        .on_conflict_do_update(
            index_elements=[AssetValuation.asset_id, AssetValuation.as_of_date],
            set_={"value": value},
        )
    )
    await session.execute(upsert_stmt)


async def refresh_prices(session: AsyncSession, *, force: bool) -> CryptoSyncResult:
    state = await get_or_create_sync_state(session)
    now = datetime.now(timezone.utc)

    if not force and state.last_synced_at is not None and now - state.last_synced_at < AUTO_REFRESH_INTERVAL:
        holdings = await list_holdings(session)
        return CryptoSyncResult(synced=False, last_synced_at=state.last_synced_at, holdings=[_to_read(h) for h in holdings])

    holdings = await list_holdings(session)
    error_key: Literal["unreachable"] | None = None
    if holdings:
        settings = await get_or_create_app_settings(session)
        try:
            prices = await _fetch_prices_batch([h.coingecko_id for h in holdings], settings.currency.lower())
        except httpx.HTTPError:
            # CoinGecko down/rate-limited — don't touch last_synced_at (the
            # next open of the tab retries) and don't touch any existing
            # AssetValuation. The tab still shows the last known values
            # instead of an empty/broken page over an external outage.
            error_key = "unreachable"
        else:
            today = date_.today()
            for holding in holdings:
                price = prices.get(holding.coingecko_id)
                if price is None:
                    continue  # coin missing from the response — keep its last known value, don't zero it out
                await _upsert_valuation(session, holding.asset_id, holding.quantity * price, today)

    if error_key is None:
        state.last_synced_at = now
    await session.commit()

    holdings = await list_holdings(session)  # re-fetch so the response carries whatever was just written
    return CryptoSyncResult(
        synced=error_key is None,
        last_synced_at=state.last_synced_at,
        error_key=error_key,
        holdings=[_to_read(h) for h in holdings],
    )


async def create_holding(session: AsyncSession, payload: CryptoHoldingCreate) -> CryptoHoldingRead:
    settings = await get_or_create_app_settings(session)

    asset = Asset(
        name=payload.name,
        asset_class=AssetClass.CRYPTO,
        currency=settings.currency,
        capital_role=CapitalRole.NEUTRAL,
        # Defaults to HIGH, not the Asset model's own MEDIUM default — matches
        # this app's own risk-level copy, which names crypto as the textbook
        # HIGH example (see lib/i18n.ts's netWorth.riskLevelFormHint.high).
        risk_level=RiskLevel.HIGH,
    )
    session.add(asset)
    await session.flush()

    holding = CryptoHolding(
        asset_id=asset.id,
        coingecko_id=payload.coingecko_id,
        symbol=payload.symbol.upper(),
        name=payload.name,
        thumb_url=payload.thumb_url,
        quantity=payload.quantity,
    )
    session.add(holding)

    # Seed today's value immediately — a coin the user just added sitting at
    # 0 until tomorrow's auto-sync would be confusing, and this one call is
    # clearly justified by an explicit user action.
    try:
        prices = await _fetch_prices_batch([payload.coingecko_id], settings.currency.lower())
        price = prices.get(payload.coingecko_id)
        if price is not None:
            await _upsert_valuation(session, asset.id, payload.quantity * price, date_.today())
        # This counts as a real sync — bump the shared timestamp so the next
        # GET /crypto/holdings doesn't immediately re-fetch every holding
        # again a moment later (see refresh_prices' 24h window).
        state = await get_or_create_sync_state(session)
        state.last_synced_at = datetime.now(timezone.utc)
    except httpx.HTTPError:
        pass  # holding is still created — the next daily/manual sync will price it

    await session.commit()

    result = await session.execute(select(CryptoHolding).options(*_EAGER).where(CryptoHolding.asset_id == asset.id))
    return _to_read(result.scalar_one())


async def update_holding_quantity(session: AsyncSession, asset_id: int, quantity: Decimal) -> CryptoHoldingRead:
    result = await session.execute(select(CryptoHolding).options(*_EAGER).where(CryptoHolding.asset_id == asset_id))
    holding = result.scalar_one_or_none()
    if holding is None:
        raise HTTPException(status_code=404, detail="Crypto holding not found")

    latest = holding.asset.valuations[-1] if holding.asset.valuations else None
    if latest is not None and holding.quantity:
        # Recompute from the last known unit price — editing quantity must
        # NOT call CoinGecko (see module docstring: only the button, adding
        # a coin, and the once-a-day check are allowed to).
        unit_price = latest.value / holding.quantity
        await _upsert_valuation(session, asset_id, quantity * unit_price, date_.today())

    holding.quantity = quantity
    await session.commit()

    # populate_existing=True — see list_holdings()'s comment: the AssetValuation
    # loaded above (before _upsert_valuation's raw Core write) is otherwise
    # served stale here.
    result = await session.execute(
        select(CryptoHolding)
        .options(*_EAGER)
        .where(CryptoHolding.asset_id == asset_id)
        .execution_options(populate_existing=True)
    )
    return _to_read(result.scalar_one())
