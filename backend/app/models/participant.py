"""Who a transaction is for — a household member or a pet.

A dimension, not a category branch. Cat food is both "Питомцы → Корм" and
"for Мурзик"; folding the animal's name into the category tree would mean
duplicating that whole branch for every additional pet, which is exactly how
the source spreadsheet ended up with 166 subcategories, 43 of them never
used once. Adding a third cat here costs one row and leaves the category
tree untouched.

The field is optional on a transaction on purpose: a bank fee, loan interest
or annual card charge belongs to nobody, and forcing a participant would
push the user to pick one at random and ruin the breakdown.
"""
from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ParticipantKind
from app.models.mixins import TimestampMixin


class Participant(Base, TimestampMixin):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    kind: Mapped[ParticipantKind] = mapped_column(
        Enum(ParticipantKind, name="participant_kind", native_enum=False, length=10),
        nullable=False,
        default=ParticipantKind.PERSON,
    )
    # Hex color for the participant chip in lists and reports.
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
