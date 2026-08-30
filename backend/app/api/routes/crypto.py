from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.crypto import CryptoHoldingCreate, CryptoHoldingRead, CryptoHoldingUpdate, CryptoSearchResult, CryptoSyncResult
from app.services.crypto_service import create_holding, refresh_prices, search_coins, update_holding_quantity

router = APIRouter(prefix="/crypto", tags=["crypto"])


@router.get("/holdings", response_model=CryptoSyncResult)
async def read_holdings(session: AsyncSession = Depends(get_session)) -> CryptoSyncResult:
    """Opening the Crypto tab lands here — this is also where the lazy
    once-a-day auto-refresh happens (see services/crypto_service.py):
    prices only actually get re-fetched from CoinGecko if 24h have passed
    since the last sync, otherwise this just reads the current cache."""
    return await refresh_prices(session, force=False)


@router.post("/refresh", response_model=CryptoSyncResult)
async def refresh_holdings(session: AsyncSession = Depends(get_session)) -> CryptoSyncResult:
    """The "Refresh prices" button — always hits CoinGecko regardless of
    the once-a-day window."""
    return await refresh_prices(session, force=True)


@router.post("/holdings", response_model=CryptoHoldingRead, status_code=201)
async def create_holding_route(
    payload: CryptoHoldingCreate, session: AsyncSession = Depends(get_session)
) -> CryptoHoldingRead:
    return await create_holding(session, payload)


@router.patch("/holdings/{asset_id}", response_model=CryptoHoldingRead)
async def update_holding_route(
    asset_id: int, payload: CryptoHoldingUpdate, session: AsyncSession = Depends(get_session)
) -> CryptoHoldingRead:
    return await update_holding_quantity(session, asset_id, payload.quantity)


@router.get("/search", response_model=list[CryptoSearchResult])
async def search_coins_route(q: str = Query(min_length=1, max_length=100)) -> list[CryptoSearchResult]:
    return await search_coins(q)
