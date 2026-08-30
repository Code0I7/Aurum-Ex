"""Crypto holdings: a thin layer on top of the existing Asset/AssetValuation
engine (see models/asset.py) rather than a parallel system. A CryptoHolding
only records identity (which coin) and quantity (how much) — the actual
value lives as ordinary AssetValuation rows, kept current by
services/crypto_service.py, so Net Worth requires zero changes to treat a
crypto holding like any other manually tracked asset.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.asset import Asset
from app.models.mixins import TimestampMixin


class CryptoHolding(Base, TimestampMixin):
    """1:1 extension of an Asset (asset_class=CRYPTO) — asset_id doubles as
    this table's own primary key rather than a separate id+unique
    constraint, so the relationship can never drift into a 1:many by
    accident. Deleting the Asset (the existing DELETE /assets/{id}) cascades
    here too — there's no separate delete endpoint for a holding."""

    __tablename__ = "crypto_holdings"

    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)

    # CoinGecko's stable coin id (e.g. "bitcoin") — NOT the ticker symbol,
    # which collides across unrelated coins (CoinGecko lists dozens of
    # differently-named coins that all use e.g. "SOL"-like tickers).
    coingecko_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # Denormalized from CoinGecko at add-time so the holdings list can
    # render a ticker/name/logo without an extra lookup per row.
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    thumb_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Bitcoin has 8 decimal places; several tokens go to 18 (wei-level
    # amounts). Deliberately NOT Numeric(14, 2) like every money field in
    # this app — this is a coin count, not a currency amount.
    quantity: Mapped[Numeric] = mapped_column(Numeric(38, 18), nullable=False)

    asset: Mapped["Asset"] = relationship()


class CryptoSyncState(Base):
    """Singleton row (id=1, same get-or-create pattern as AppSettings) — the
    single global timestamp of the last successful CoinGecko price refresh.
    One timestamp for every holding, not one per holding: a refresh always
    re-prices every tracked coin in a single batched request (see
    services/crypto_service.py), so there's only ever one "last synced"
    moment to track."""

    __tablename__ = "crypto_sync_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
