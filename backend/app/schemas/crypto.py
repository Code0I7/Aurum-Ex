from datetime import date as date_
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CryptoTransactionType


class CryptoTransactionCreate(BaseModel):
    type: CryptoTransactionType
    quantity: Decimal = Field(gt=0, max_digits=38, decimal_places=18)
    # Price paid (buy) / received (sell) per unit, in the app's display
    # currency — not fetched from CoinGecko, this is what the user actually
    # paid, which the market price today has nothing to do with.
    price_per_unit: Decimal = Field(gt=0, max_digits=38, decimal_places=18)
    date: date_
    note: str | None = Field(default=None, max_length=500)


class CryptoTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    type: CryptoTransactionType
    quantity: Decimal
    price_per_unit: Decimal
    date: date_
    note: str | None


class CryptoHoldingCreate(BaseModel):
    coingecko_id: str = Field(min_length=1, max_length=100)
    symbol: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=150)
    thumb_url: str | None = Field(default=None, max_length=500)
    # A holding always starts with a buy — there's nothing to "start
    # tracking" with a sell.
    quantity: Decimal = Field(gt=0, max_digits=38, decimal_places=18)
    price_per_unit: Decimal = Field(gt=0, max_digits=38, decimal_places=18)
    date: date_ = Field(default_factory=date_.today)
    note: str | None = Field(default=None, max_length=500)


class CryptoHoldingRead(BaseModel):
    asset_id: int
    coingecko_id: str
    symbol: str
    name: str
    thumb_url: str | None

    # Quantity and avg_buy_price are derived from the transaction log (see
    # services/crypto_service.py's _compute_position) — never stored.
    quantity: Decimal
    avg_buy_price: Decimal | None

    # Cached from the last successful CoinGecko sync — null until the
    # first one completes.
    current_price: Decimal | None
    price_change_1h: Decimal | None
    price_change_24h: Decimal | None
    price_change_7d: Decimal | None

    # All derived from the above: value = current_price * quantity,
    # cost_basis = avg_buy_price * quantity, profit_loss = value - cost_basis.
    value: Decimal | None
    cost_basis: Decimal | None
    profit_loss: Decimal | None
    profit_loss_percent: float | None


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
