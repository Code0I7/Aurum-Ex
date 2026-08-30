from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.crypto import (
    CryptoHistoryResponse,
    CryptoHoldingCreate,
    CryptoHoldingRead,
    CryptoSearchResult,
    CryptoSyncResult,
    CryptoTransactionCreate,
    CryptoTransactionRead,
)
from app.services.crypto_service import (
    CRYPTO_RANGE_DAYS,
    add_transaction,
    create_holding,
    delete_transaction,
    get_crypto_history,
    list_transactions,
    refresh_prices,
    search_coins,
)

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


@router.post("/holdings/{asset_id}/transactions", response_model=CryptoHoldingRead, status_code=201)
async def add_transaction_route(
    asset_id: int, payload: CryptoTransactionCreate, session: AsyncSession = Depends(get_session)
) -> CryptoHoldingRead:
    """Buy more of, or sell some of, a coin already being tracked."""
    return await add_transaction(session, asset_id, payload)


@router.get("/holdings/{asset_id}/transactions", response_model=list[CryptoTransactionRead])
async def list_transactions_route(
    asset_id: int, session: AsyncSession = Depends(get_session)
) -> list[CryptoTransactionRead]:
    return await list_transactions(session, asset_id)


@router.delete("/transactions/{transaction_id}", status_code=204)
async def delete_transaction_route(transaction_id: int, session: AsyncSession = Depends(get_session)) -> None:
    await delete_transaction(session, transaction_id)


@router.get("/search", response_model=list[CryptoSearchResult])
async def search_coins_route(q: str = Query(min_length=1, max_length=100)) -> list[CryptoSearchResult]:
    return await search_coins(q)


_HISTORY_RANGES = sorted(set(CRYPTO_RANGE_DAYS) | {"all"})
_HISTORY_RANGE_PATTERN = f"^({'|'.join(_HISTORY_RANGES)})$"


@router.get("/history", response_model=CryptoHistoryResponse)
async def read_crypto_history(
    range: str = Query(default="30d", pattern=_HISTORY_RANGE_PATTERN),
    session: AsyncSession = Depends(get_session),
) -> CryptoHistoryResponse:
    return await get_crypto_history(session, range)
