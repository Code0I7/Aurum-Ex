"""Investments held in lots, with disposals matched FIFO.

One engine for every asset family — shares, bonds, funds, crypto, metals
(see InvestmentKind). Lots, cost basis and disposal are identical arithmetic
for a share and a coin, so keeping two parallel modules would only mean
fixing every bug twice; the tab a holding appears under is a filter, not a
separate system.

FIFO, not weighted average — a deliberate change from the crypto module this
replaces, which blended every buy into a running average price. The two
methods disagree by an order of magnitude on the same trade:

    Куплено:  1 шт по 500 ₽, затем 5 шт по 100 ₽  →  6 шт за 1 000 ₽
    Продано:  2 шт по 150 ₽                       →  выручка 300 ₽

    FIFO:     списываются самые старые (500 + 100 = 600)  →  убыток 300 ₽
    Средняя:  1000 / 6 = 166,67 за штуку (333 ₽)          →  убыток 33 ₽

FIFO is what a Russian broker's own report and the tax authority both use,
so the numbers here reconcile with the numbers in the broker's app instead
of quietly contradicting them. Having one method across the whole app also
prevents the worse outcome: two adjacent tabs disagreeing about identical
operations.

Prices are entered by hand, with an optional external id (`external_id`) for
sources that can be polled — the crypto module already refreshes quotes
daily, and that mechanism carries over unchanged.
"""
from datetime import date as date_
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import InvestmentKind, RiskLevel, TradeSide
from app.models.mixins import TimestampMixin


class InvestmentPortfolio(Base, TimestampMixin):
    """A user-defined grouping — "долгосрок", "спекуляции", "пенсия".
    Carried over from the crypto module's portfolios, widened to all kinds:
    the same instrument may be held in more than one portfolio and tracked
    separately in each."""

    __tablename__ = "investment_portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    holdings: Mapped[list["InvestmentHolding"]] = relationship(back_populates="portfolio")


class InvestmentHolding(Base, TimestampMixin):
    """One instrument inside one portfolio. Quantity and cost basis are never
    stored — they are replayed from the trade log, the same "record it, we
    derive it" shape the app uses for account balances and goals. Storing a
    running total would mean two sources of truth that drift apart the first
    time a trade is edited."""

    __tablename__ = "investment_holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("investment_portfolios.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # Тикер или короткий код: ACME, BTC, XAU.
    ticker: Mapped[str | None] = mapped_column(String(30), nullable=True)
    kind: Mapped[InvestmentKind] = mapped_column(
        Enum(InvestmentKind, name="investment_kind", native_enum=False, length=10), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")

    # Идентификатор во внешнем источнике котировок (например, id монеты в
    # CoinGecko). Пусто — цена вводится руками.
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Последняя известная цена за единицу и когда она получена. Хранится,
    # чтобы страница открывалась мгновенно, не дожидаясь внешнего запроса.
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    last_price_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, name="investment_risk_level", native_enum=False, length=10),
        nullable=False,
        default=RiskLevel.MEDIUM,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    portfolio: Mapped["InvestmentPortfolio"] = relationship(back_populates="holdings")
    trades: Mapped[list["InvestmentTrade"]] = relationship(
        back_populates="holding", cascade="all, delete-orphan", order_by="InvestmentTrade.trade_date"
    )


class InvestmentTrade(Base, TimestampMixin):
    """One buy or sell. The FIFO replay walks these in date order: a BUY
    opens a lot, a SELL consumes the oldest open lots until its quantity is
    covered, and the realised profit is the difference between what those
    lots cost and what they sold for.

    Ties inside one day are broken by `day_order`, then by id — the same
    problem the transactions table has, and for the same reason: two trades
    dated the same day must not swap places between page loads, or the
    realised profit would change on refresh."""

    __tablename__ = "investment_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    holding_id: Mapped[int] = mapped_column(
        ForeignKey("investment_holdings.id", ondelete="CASCADE"), nullable=False
    )

    side: Mapped[TradeSide] = mapped_column(
        Enum(TradeSide, name="trade_side", native_enum=False, length=10), nullable=False
    )
    # Крипта дробится до восьми знаков, акции — целые. Общий тип покрывает оба.
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    price_per_unit: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    # Комиссия брокера. Входит в стоимость покупки и уменьшает выручку от
    # продажи — иначе доходность окажется завышенной.
    fee: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))

    trade_date: Mapped[date_] = mapped_column(Date, nullable=False)
    day_order: Mapped[int] = mapped_column(nullable=False, default=0)

    # Счёт, с которого ушли или на который пришли деньги. Необязателен: до
    # шестого этапа брокерский счёт можно не заводить вовсе.
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    holding: Mapped["InvestmentHolding"] = relationship(back_populates="trades")
    account: Mapped["Account | None"] = relationship()
