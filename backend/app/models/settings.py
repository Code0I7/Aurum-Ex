"""App-wide configuration that isn't tied to any single account/asset — a
single-row table (id is always 1). Primary display currency and the
proactive-alert thresholds consumed by services/insights_service.py.

The original comment here pointed at UPDATES.md to explain why currency
conversion did not happen; it does now, so `currency` has become the base
currency every amount is converted *to* rather than a label printed next to
unconverted numbers. See models/currency.py for how rates are fetched and
which rate applies where.
"""
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import Date, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Базовая валюта: в неё приводятся все суммы для сводных цифр. Курс
    # самой базовой валюты к себе всегда ровно 1 и нигде не хранится —
    # именно попытка его материализовать давала в исходной таблице
    # RUBRUB = 0,9999995974 и копеечные расхождения, которые приходилось
    # править вручную.
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")

    # Дата, с которой учёт считается достоверным. Данные до неё остаются в
    # истории и в балансах, но в средние, тренды и стоимость часа не входят.
    # Нужна потому, что учёт почти всегда начинается неровно: в исходных
    # данных январь–март 2024 содержат по 4–7 записей на месяц, а апрель,
    # май и июнь — ни одной. Без такой границы приложение годами рисовало бы
    # "рост расходов", который на деле есть рост качества записи.
    reliable_from: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    # Consecutive complete months of negative cash flow / declining net worth
    # before insights_service.py raises the corresponding alert.
    negative_cash_flow_threshold_months: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    net_worth_decline_threshold_months: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    # Max % of total capital (cash + assets) allowed in medium/high risk
    # tiers before insights_service.py raises risky_allocation_exceeded —
    # the classic "80% at zero risk, 20% at most exposed" rule.
    risky_allocation_threshold_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    # A depository account (checking/savings/cash) sitting at or above this
    # balance with no transaction touching it in idle_cash_threshold_days
    # raises insights_service.py's idle_cash alert — money that isn't
    # working. In the app's display currency (see `currency` above).
    idle_cash_threshold_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("1000"))
    idle_cash_threshold_days: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
