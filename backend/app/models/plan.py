"""A planned amount for a category — what the user intends to spend or earn,
against which the actual figures are compared.

Different from Budget (models/budget.py), and both exist. A budget is a
monthly ceiling that raises a warning when crossed; a plan is an expectation
stretched over years, used to answer "what will the year look like" rather
than "am I over the limit right now".

Three shapes, because the source spreadsheet needed three and had to fake
two of them by typing a number into every month by hand:

  * ONE_OFF — машина в мае 2027: одна сумма в один месяц;
  * MONTHLY — связь 700 ₽: одно и то же каждый месяц, пока не изменишь;
  * DAILY — столовая 300 ₽ в день: сумма умножается на число дней месяца,
    а при `workdays_only` — только на рабочие, и в феврале пересчитывается
    сама.

No automatic indexation anywhere. When a price rises the user edits the
number and it applies from that month forward — the past is never rewritten.
Гибкость тут стоила бы точности: "связь дорожает на 5% в год" звучит умно,
но в жизни цена меняется рывками и в непредсказуемые месяцы.
"""
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import PlanKind
from app.models.mixins import TimestampMixin


class Plan(Base, TimestampMixin):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Категория, к которой относится план. SET NULL, как и везде: удаление
    # категории не должно ломать чтение плана.
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    # Персона, если план личный. Пусто — план общий по домохозяйству.
    participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("participants.id", ondelete="SET NULL"), nullable=True
    )

    kind: Mapped[PlanKind] = mapped_column(
        Enum(PlanKind, name="plan_kind", native_enum=False, length=10), nullable=False
    )
    # Для ONE_OFF и MONTHLY — сумма на месяц, для DAILY — сумма на день.
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")

    # Период действия. Для ONE_OFF обе даты попадают в один месяц; для
    # MONTHLY и DAILY `valid_to` пустая, пока план не отменён, — так одна
    # запись покрывает сколько угодно лет вперёд.
    valid_from: Mapped[date_] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date_ | None] = mapped_column(Date, nullable=True)

    # Только для DAILY: считать рабочие дни вместо календарных. Рабочая
    # столовая по выходным не работает, и календарные дни завышали бы план
    # почти в полтора раза.
    workdays_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    category: Mapped["Category | None"] = relationship()
    participant: Mapped["Participant | None"] = relationship()
