"""Units of measure, each convertible to the base unit of its kind.

The conversion factor is the whole point. Without it "1.5 л сока за 120 ₽"
and "500 мл сока за 55 ₽" cannot be compared, and price tracking degrades
into guesswork — which is why the source spreadsheet's quantity columns went
unused in 89% of its records: its units (Шт, Опл, Бут, Уп, Кг, Л, Бнк, М)
were labels with no arithmetic behind them.

Every unit stores how many base units it equals: кг → 1000 (base грамм),
л → 1000 (base миллилитр), шт → 1 (base штука). Price per base unit is then
just amount / (quantity * factor), and litres compare with millilitres for
free.

SERVICE-kind units (оплата, подписка) have factor 1 and a quantity that is
always 1 — they exist so a taxi ride or a music subscription can be recorded
without pretending it has a weight.
"""
from decimal import Decimal

from sqlalchemy import Boolean, Enum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import UnitKind
from app.models.mixins import TimestampMixin


class Unit(Base, TimestampMixin):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Short label shown in the transaction row: "кг", "л", "шт".
    name: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    kind: Mapped[UnitKind] = mapped_column(
        Enum(UnitKind, name="unit_kind", native_enum=False, length=10), nullable=False
    )
    # How many base units of this kind one of these equals: кг → 1000 г.
    # Numeric rather than float so 0.001-style factors stay exact.
    factor: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("1"))
    # The base unit of its kind (грамм, миллилитр, штука). Exactly one per
    # kind should carry this flag — it is what price-per-unit is quoted in.
    is_base: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
