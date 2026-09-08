"""A savings goal, tracked by a manual contribution log (GoalContribution) —
same "you record it, we sum it" shape as Asset/AssetValuation, except
contributions are deltas added together, not point-in-time snapshots.

Extended into an envelope: a goal now points at the account the money
actually sits on, and its balance is a *reservation* inside that account's
balance rather than a separate pot. The account then reads as three
numbers — всего на счету, отложено, доступно — which is honest, because the
money never went anywhere.

This replaces a costly workaround. Spreadsheets usually build the same idea out of a
fictitious "savings" account plus paired transfer rows, so putting money
aside takes three records and spending it takes four — well over a dozen
rows for a single planned purchase. The system works and is simply too
expensive to use often, which is why such goals stay rare.

Goals also end in two opposite ways, which the spreadsheet could not tell
apart because both were an "Изъять" row distinguished only by its comment:
five of its fifteen goals ended by giving up and returning the money. Hence
GoalStatus (see models/enums.py) — ACHIEVED spends the reservation,
CANCELLED merely releases it.
"""
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import GoalStatus
from app.models.mixins import TimestampMixin


class Goal(Base, TimestampMixin):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    target_date: Mapped[date_ | None] = mapped_column(Date, nullable=True)

    # Счёт, на котором физически лежат отложенные деньги. Необязателен:
    # цель можно вести и без привязки, тогда она остаётся просто планом
    # накопления и ничего не резервирует.
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)

    status: Mapped[GoalStatus] = mapped_column(
        Enum(GoalStatus, name="goal_status", native_enum=False, length=10),
        nullable=False,
        default=GoalStatus.ACTIVE,
    )
    # Дата закрытия цели — достигнута или отменена. Пусто, пока копится.
    closed_at: Mapped[date_ | None] = mapped_column(Date, nullable=True)

    account: Mapped["Account | None"] = relationship()
    contributions: Mapped[list["GoalContribution"]] = relationship(
        back_populates="goal", cascade="all, delete-orphan", order_by="GoalContribution.date"
    )


class GoalContribution(Base):
    """One deposit (or, with a negative amount, a withdrawal) toward a goal.
    A goal's current amount is the sum of all its contributions.

    A contribution moves no money — it only marks part of the account's
    balance as spoken for. Отрицательная сумма снимает резерв: так
    записывается и отказ от цели, и трата отложенного."""

    __tablename__ = "goal_contributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    date: Mapped[date_] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Счёт, с которого отложены эти деньги. Раньше счёт был у самой
    # цели — один на всё накопление, — и «три тысячи наличными, две
    # безналом» этим не выражалось. Резерв ведётся по каждому счёту
    # отдельно: иначе вернуть с наличных можно было бы больше, чем с них
    # откладывали, а такой возврат — это не ошибка ввода, а испорченный
    # остаток на счёте.
    #
    # SET NULL: удаление счёта не стирает историю накопления. Взнос
    # останется, просто перестанет что-либо резервировать.
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )

    # Счёт, с которого отложены эти деньги. Раньше счёт был у самой
    # цели — один на всё накопление, — и «три тысячи наличными, две
    # безналом» этим не выражалось. Резерв ведётся по каждому счёту
    # отдельно: иначе вернуть с наличных можно было бы больше, чем с них
    # откладывали, а такой возврат — это не ошибка ввода, а испорченный
    # остаток на счёте.
    #
    # SET NULL: удаление счёта не стирает историю накопления. Взнос
    # останется, просто перестанет что-либо резервировать.
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )

    # Трата, которой цель была реализована. Заполняется, когда деньги
    # действительно ушли на то, ради чего копились: обычный расход с
    # отметкой "из цели", а не отдельная механика. SET NULL — удаление
    # покупки не должно стирать историю накопления.
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )

    goal: Mapped["Goal"] = relationship(back_populates="contributions")
    transaction: Mapped["Transaction | None"] = relationship()
