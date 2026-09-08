from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class AppSettingsRead(BaseModel):
    currency: str
    negative_cash_flow_threshold_months: int
    net_worth_decline_threshold_months: int
    risky_allocation_threshold_percent: int
    idle_cash_threshold_amount: Decimal
    idle_cash_threshold_days: int

    # Что показывать при открытии. Настраивается один раз и хранится на
    # сервере: установка однопользовательская, и выбор, сделанный на
    # ноутбуке, должен действовать с телефона.
    default_dashboard_range: str = "year"
    # Счёт, подставляемый в новую операцию. Пусто — подставлять нечего, и
    # человек выбирает счёт сам, как раньше.
    default_account_id: int | None = None
    default_page_size: int = 50
    group_repeats_by_default: bool = True
    day_dividers_by_default: bool = True


class AppSettingsUpdate(BaseModel):
    """All fields optional — the route applies a partial update
    (`exclude_unset`), same as CategoryUpdate, so a single-field PATCH from
    e.g. CurrencyCard doesn't need to resend the alert thresholds."""

    # ISO 4217 code, e.g. "USD"/"UAH"/"EUR" — the frontend only ever sends
    # values from its curated currency list, but validate the shape anyway
    # since Intl.NumberFormat would otherwise silently accept garbage.
    currency: str | None = Field(default=None, min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    # Consecutive complete months before the corresponding alert fires.
    # Capped at 24 to match insights_service.py's MAX_LOOKBACK_MONTHS.
    negative_cash_flow_threshold_months: int | None = Field(default=None, ge=1, le=24)
    net_worth_decline_threshold_months: int | None = Field(default=None, ge=1, le=24)
    # Max % of capital allowed in medium/high risk tiers (the 80/20 rule's
    # "20% at most exposed" half) before risky_allocation_exceeded fires.
    risky_allocation_threshold_percent: int | None = Field(default=None, ge=1, le=100)
    # Balance (in the app's display currency) and days of no activity a
    # depository account needs to hit before idle_cash fires.
    idle_cash_threshold_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    idle_cash_threshold_days: int | None = Field(default=None, ge=1, le=365)

    # Период дашборда при открытии: month, year или all.
    default_dashboard_range: Literal["month", "year", "all"] | None = None
    default_account_id: int | None = None
    # Сколько операций подгружать за раз. Верхняя граница есть: страница на
    # тысячу строк грузится дольше, чем прокручиваются пятьдесят.
    default_page_size: int | None = Field(default=None, ge=10, le=500)
    group_repeats_by_default: bool | None = None
    day_dividers_by_default: bool | None = None
