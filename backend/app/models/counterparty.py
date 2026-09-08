"""Someone outside the household whose money passes through your accounts:
a spouse sending grocery money, a friend borrowing until payday, a parent
being helped out.

Deliberately NOT an Account. A counterparty's running total is not capital
and must never reach net worth — the balance here answers "how much has
this person handed me in total", which is useful, but it is somebody else's
money, not yours. Keeping them out of Account is what lets that total sit
happily at a large negative number without polluting a single report.

This replaces the usual spreadsheet workaround, where money handed over by
a spouse gets booked through placeholder income and expense categories so
it does not inflate real earnings. Здесь для этого есть собственные виды
операций — EXTERNAL_IN и EXTERNAL_OUT.

Counterparties are created inline while typing a transaction, never up
front: there may be three of them or two hundred, and a list nobody has to
prepare in advance costs nothing either way.
"""
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Counterparty(Base, TimestampMixin):
    __tablename__ = "counterparties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
