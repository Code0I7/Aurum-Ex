"""Currencies in use and their exchange rates against the base currency.

Rates come from the Central Bank of Russia's dated endpoint
(`XML_daily.asp?date_req=DD.MM.YYYY`) — an official machine-readable source
that needs no API key and reaches back to 1992. Parsing the bank's HTML was
never on the table: a layout change would break it silently, while this
address has been stable for years.

Two rules make multi-currency behave sanely, and they pull in opposite
directions on purpose:

  * a TRANSACTION is converted at the rate of the day it happened, and that
    rate is copied into the transaction row itself — so an expense of 100 $
    in 2022 stays 6 026 ₽ in the 2022 report forever, no matter what the
    dollar does afterwards. The past does not get rewritten.
  * a BALANCE is converted at today's rate — 50 $ sitting on an account are
    worth what they are worth right now.

Only days that actually carry an operation are stored. The source
spreadsheet kept all 25 currency pairs for all 1471 days — roughly 36 000
GOOGLEFINANCE calls recomputed on every open — and used none of them, which
is the single biggest reason it became slow to work with.

The CBR publishes nothing on weekends and holidays; the last working day's
rate carries over, which is what the spreadsheet did too via WORKDAY().
"""
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import Boolean, Date, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Currency(Base, TimestampMixin):
    """A currency the user actually holds or spends in. Seeded with the base
    currency alone; the rest are added when a first account or transaction
    needs them."""

    __tablename__ = "currencies"

    # ISO 4217 alphabetic code as the primary key — "RUB", "USD". Natural,
    # stable, and readable in every foreign key that points here.
    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    # Symbol shown in the UI: ₽, $, €. Falls back to the code when absent.
    symbol: Mapped[str | None] = mapped_column(String(8), nullable=True)
    name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # ЦБ котирует валюты за лот: доллар за 1, а иена, например, за 100.
    # Хранится, чтобы курс приводился к одной единице при разборе ответа.
    cbr_nominal: Mapped[int] = mapped_column(nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ExchangeRate(Base):
    """One currency's rate against the base currency on one date.

    Stored as "how many base-currency units one unit of `code` is worth", so
    a rouble-based install holding dollars keeps 86.53788 rather than its
    reciprocal — the direction the CBR publishes and a human can sanity-check
    at a glance. The base currency itself is never stored here: its rate is
    always exactly 1, and materialising it is what produced the source
    spreadsheet's RUBRUB = 0.9999995974 and the rounding drift the user kept
    correcting by hand.
    """

    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint("code", "rate_date", name="uq_exchange_rate_code_date"),
        Index("ix_exchange_rate_date", "rate_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(3), nullable=False)
    rate_date: Mapped[date_] = mapped_column(Date, nullable=False)
    # 10 знаков после запятой: у слабых валют курс к рублю — это доли копейки.
    rate: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    # Дата, на которую курс реально опубликован. В выходные совпадает с
    # последним рабочим днём, а не с `rate_date` — чтобы было видно, что
    # значение перенесено, а не получено на эту дату.
    published_for: Mapped[date_ | None] = mapped_column(Date, nullable=True)
