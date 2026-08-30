from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CryptoHoldingCreate(BaseModel):
    coingecko_id: str = Field(min_length=1, max_length=100)
    symbol: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=150)
    thumb_url: str | None = Field(default=None, max_length=500)
    # 18 decimal places covers wei-level token amounts; still gt=0 since a
    # zero/negative holding isn't a holding.
    quantity: Decimal = Field(gt=0, max_digits=38, decimal_places=18)


class CryptoHoldingUpdate(BaseModel):
    quantity: Decimal = Field(gt=0, max_digits=38, decimal_places=18)


class CryptoHoldingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: int
    coingecko_id: str
    symbol: str
    name: str
    thumb_url: str | None
    quantity: Decimal
    # Both derived from the linked Asset's latest AssetValuation — null
    # value/unit_price means "added but never priced yet" (CoinGecko was
    # unreachable at creation time), not zero.
    value: Decimal | None
    unit_price: Decimal | None
    as_of_date: str | None


class CryptoSyncResult(BaseModel):
    # False when the lazy daily check ran but the 24h window hadn't
    # elapsed yet (nothing called CoinGecko this time, error_key is None),
    # OR when a refresh was attempted but CoinGecko couldn't be reached
    # (error_key is set) — check error_key to tell the two apart. Either
    # way `holdings` still carries the best data on hand, never blocked by
    # an external outage.
    #
    # A key, not a message string: the frontend translates it (RU/EN), same
    # key+params convention as FinancialAlert/AdviceItem — a raw English
    # sentence here would silently break the app's bilingual UI.
    synced: bool
    last_synced_at: datetime | None
    error_key: Literal["unreachable"] | None = None
    holdings: list[CryptoHoldingRead]


class CryptoSearchResult(BaseModel):
    coingecko_id: str
    symbol: str
    name: str
    thumb_url: str | None
