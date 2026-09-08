"""Working hours per month, per participant — the denominator behind
"сколько часов жизни стоила эта покупка".

The metric itself is the most sobering thing the source spreadsheet had, and
also the one it computed wrong. Hours were entered once per *year* (1482,
1235, 2232, 2218) and divided into that year's income even when the year was
half empty:

    2022: 30 211 ₽ ÷ 1482 ч = 20,39 ₽/ч   — но работал он 5 месяцев из 12
          на самом деле ≈ 49 ₽/ч, занижено в 2,4 раза
    2024: 156 022 ₽ ÷ 2232 ч = 69,90 ₽/ч  — три месяца учёта отсутствуют
          на самом деле ≈ 93 ₽/ч

Storing hours per month fixes both cases at once: an empty month simply
contributes nothing to either side of the division, and seasonality becomes
visible instead of being averaged away.

Один и тот же месяц может быть заполнен для нескольких участников — у
каждого своя загрузка, и стоимость часа считается по своему знаменателю.
"""
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class WorkPeriod(Base, TimestampMixin):
    __tablename__ = "work_periods"
    __table_args__ = (
        UniqueConstraint("participant_id", "year", "month", name="uq_work_period_participant_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Пусто — период относится к владельцу установки. Так метрика работает
    # сразу, до того как кто-то заведёт участников.
    participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=True
    )

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)

    # Дробные часы — обычное дело: 164,5 за месяц с половиной смены.
    hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=Decimal("0"))
    # Отработанные дни. Нужны не для стоимости часа, а для планов вида
    # "столовая 300 ₽ в рабочий день" (см. models/plan.py).
    workdays: Mapped[int | None] = mapped_column(Integer, nullable=True)

    participant: Mapped["Participant | None"] = relationship()
