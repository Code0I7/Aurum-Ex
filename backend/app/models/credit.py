"""Loan terms attached to an account whose nature is LIABILITY.

The account itself already models the debt correctly — a balance that goes
negative as money is borrowed and climbs back to zero as it is repaid. That
part of the source spreadsheet was not a workaround but the right shape, and
it is kept as is. What was missing is everything around it: the rate, the
grace period, the minimum payment. Without them, interest had to be worked
out by hand once a month, and the only trace it left was a category called
"Проценты по кредитам" — 18 237 ₽ in 2025 against 55 846 ₽ of principal, a
third again on top, discovered only by adding the rows up afterwards.

A 1:1 extension of Account rather than a table of its own with a duplicate
name and balance: account_id doubles as the primary key, so the relationship
cannot silently drift into one-to-many, and deleting the account takes these
terms with it.

Interest is still posted by hand, deliberately. Banks compute it in ways no
formula here would reliably reproduce (grace periods, partial early
repayment, the exact day count), so the app's job is to remind and to
estimate — never to pretend it knows the bank's number.
"""
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class CreditTerms(Base, TimestampMixin):
    __tablename__ = "credit_terms"

    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)

    # Годовая ставка в процентах: 24.9 — это 24.9, а не 0.249. Хранится
    # так, как её называет банк, чтобы значение можно было сверить глазами.
    annual_rate_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    # Кредитный лимит — сколько всего можно занять. Нужен, чтобы показывать
    # "использовано 12 300 из 100 000", а не просто отрицательный баланс.
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    # Беспроцентный период в днях: 120 у рассрочки, 55 у типичной карты.
    grace_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # День месяца, когда банк ждёт платёж, и его минимальный размер.
    payment_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Минимальный платёж задаётся двумя числами, потому что банки так его и
    # задают: «не более 8% от задолженности, минимум 600 рублей». Процент
    # без порога и порог без процента тоже осмысленны, поэтому оба
    # необязательны и работают по отдельности.
    minimum_payment: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    minimum_payment_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    opened_on: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    closes_on: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    account: Mapped["Account"] = relationship()
    # Ставки, кроме основной. Основная остаётся в annual_rate_percent: по ней
    # считается прикидка процентов, и сводке нужна одна цифра, а не список.
    rates: Mapped[list["CreditRate"]] = relationship(
        back_populates="terms",
        cascade="all, delete-orphan",
        order_by="CreditRate.sort_order",
        lazy="selectin",
    )


class CreditRate(Base):
    """Одна строка матрицы ставок.

    В тарифе кредитной карты ставок семь, и какая применится, зависит от
    двух вещей: что за операция (покупка, снятие наличных, плата) и когда
    она была (первые тридцать дней с первой расходной операции или позже).
    Свести это к одному числу нельзя — выбранное число окажется верным для
    одной строки тарифа и неверным для шести остальных.

    Расчётам матрица не нужна: проценты приложение не начисляет, а лишь
    прикидывает по основной ставке. Она нужна человеку — в тот момент,
    когда он думает, снять ли наличные с кредитки, и не хочет открывать
    договор.
    """

    __tablename__ = "credit_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("credit_terms.account_id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Что это за операция: «Покупки», «Снятие наличных», «Платы и прочее».
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    # Когда применяется: «с 31-го дня», «в первые 30 дней», «в льготный
    # период». Необязательно: у рассрочки условие одно и описывать его
    # нечем.
    condition: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    terms: Mapped["CreditTerms"] = relationship(back_populates="rates")
