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

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String
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

    # Что показывать при открытии. Выбирается один раз, а не каждый сеанс
    # заново, и хранится на сервере, а не в браузере: установка
    # однопользовательская, и настройка с ноутбука должна действовать с
    # телефона.
    #
    # Период дашборда: month, year или all. Год по умолчанию — месяц при
    # многолетней истории случайный срез, а «за всё время» отвечает на
    # вопрос «как было вообще», тогда как открывают приложение обычно с
    # вопросом «как у меня сейчас».
    default_dashboard_range: Mapped[str] = mapped_column(String(10), nullable=False, default="year")
    # Сколько операций подгружать за раз. Пятьдесят, а не двадцать: при
    # четырёх годах истории двадцать строк — это полторы недели, и до
    # прошлого месяца приходится долистывать.
    # Счёт, который подставляется в новую операцию. Основная карта у
    # человека одна, и выбирать её каждый раз из списка — лишний шаг на
    # самом частом действии в приложении.
    #
    # SET NULL: удалённый счёт просто перестаёт подставляться, а не роняет
    # форму ввода ссылкой в пустоту.
    default_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    # Показывать ли копейки. В самой операции они и есть данные: 36,99,
    # показанные как 37, — уже не то, что записано, и список из таких строк
    # не сходится в сумму. В итогах за год копейки, наоборот, только
    # удлиняют число. Правильного ответа на оба случая нет, поэтому
    # переключатель.
    show_cents: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_page_size: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    # Склеивать ли одинаковые траты дня и рисовать ли разделители дней.
    group_repeats_by_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    day_dividers_by_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
