"""An account is any place money lives: bank account, card, cash, wallet.

Two independent axes describe it (see models/enums.py): `kind` says what
sort of place it is, `nature` says whether its balance adds to capital or
subtracts from it. They are deliberately not derived from each other — a
store instalment account is `kind=OTHER, nature=LIABILITY`, while a savings
account and cash are different kinds sharing one nature.

An account may also carry an opening balance: money already there when
tracking started. It belongs to the balance but is NOT income — booking it
as income inflates the first year's earnings and quietly ruins every
figure derived from them, "roubles per working hour" included.
"""
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AccountKind, AccountNature
from app.models.mixins import TimestampMixin


class Bank(Base, TimestampMixin):
    """A bank or payment provider holding one or more accounts. Exists so
    the accounts screen can group several cards of one bank under a single
    heading instead of listing unrelated-looking rows — grouping is the only
    job, so there is deliberately nothing here beyond a name and a color."""

    __tablename__ = "banks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    # Hex color for the group header dot, same convention as Account.color.
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    accounts: Mapped[list["Account"]] = relationship(back_populates="bank")


class Account(Base, TimestampMixin):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Renamed from `type` along with the enum — see AccountKind's docstring.
    kind: Mapped[AccountKind] = mapped_column(
        Enum(AccountKind, name="account_kind", native_enum=False, length=20),
        nullable=False,
        default=AccountKind.CHECKING,
    )
    # Asset or liability. Defaulted from `kind` at creation time in the
    # service layer (credit_card and loan default to LIABILITY), but stored
    # separately so the user can override it.
    nature: Mapped[AccountNature] = mapped_column(
        Enum(AccountNature, name="account_nature", native_enum=False, length=10),
        nullable=False,
        default=AccountNature.ASSET,
    )
    bank_id: Mapped[int | None] = mapped_column(ForeignKey("banks.id", ondelete="SET NULL"), nullable=True)

    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")

    # Money already on the account the day tracking began. Part of the
    # balance, never part of income — the formula is
    # "opening + earned - spent = balance", not "earned - spent = balance".
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    # The day the opening balance applies from. Earlier transactions are
    # allowed (imported history), but the running balance starts here.
    opening_date: Mapped[date_ | None] = mapped_column(Date, nullable=True)

    # Debit cards and cash cannot go below zero in real life, so a balance
    # that does means a lost deposit rather than an overdraft. Off by default
    # for asset accounts, on for liabilities — this is the check that catches
    # a lost deposit long before the yearly totals stop making sense.
    allow_negative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Hex color used for account-scoped UI accents (e.g. transaction list avatars).
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    bank: Mapped["Bank | None"] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="account",
        foreign_keys="Transaction.account_id",
        cascade="all, delete-orphan",
    )
