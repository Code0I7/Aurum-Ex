"""Схемы планирования.

Сумма означает разное в зависимости от вида плана: для разового и
ежемесячного — сумму на месяц, для ежедневного — на день. Одно поле вместо
двух намеренно: два поля пришлось бы держать согласованными, и рано или
поздно они разошлись бы.
"""
from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import CategoryKind, PlanKind


class PlanBase(BaseModel):
    category_id: int | None = None
    participant_id: int | None = None
    kind: PlanKind
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    valid_from: date_
    valid_to: date_ | None = None
    workdays_only: bool = False
    note: str | None = Field(default=None, max_length=200)
    is_active: bool = True

    @model_validator(mode="after")
    def check_period(self) -> "PlanBase":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not be earlier than valid_from")
        # Признак «только рабочие дни» имеет смысл лишь у ежедневного плана.
        # Молча его игнорировать нельзя: человек, поставивший галочку на
        # ежемесячном плане, ждал другого поведения.
        if self.workdays_only and self.kind is not PlanKind.DAILY:
            raise ValueError("workdays_only applies to daily plans only")
        return self


class PlanCreate(PlanBase):
    pass


class PlanUpdate(BaseModel):
    category_id: int | None = None
    participant_id: int | None = None
    kind: PlanKind | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    valid_from: date_ | None = None
    valid_to: date_ | None = None
    workdays_only: bool | None = None
    note: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None


class PlanRead(PlanBase):
    id: int
    # Название категории кладётся рядом, чтобы список планов не требовал
    # второго запроса ради одной подписи.
    category_name: str | None = None

    model_config = {"from_attributes": True}


class MonthCellOut(BaseModel):
    month: int
    planned: Decimal
    actual: Decimal
    # Факт минус план. Для расхода минус означает экономию, для дохода —
    # недобор, поэтому подпись знака остаётся за интерфейсом: он знает вид
    # строки.
    deviation: Decimal


class PlanRowOut(BaseModel):
    category_id: int | None
    name: str
    kind: CategoryKind
    months: list[MonthCellOut]
    planned_total: Decimal
    actual_total: Decimal


class WatchRowOut(BaseModel):
    category_id: int
    name: str
    # «Продукты · Сладкое» — путь до корня ветки: имена категорий не
    # уникальны, и без пути две одинаковые строки не различить.
    path: str
    kind: CategoryKind
    # Двенадцать сумм, январь — декабрь.
    months: list[Decimal]
    total: Decimal
    previous_total: Decimal


class WatchlistOut(BaseModel):
    """Список наблюдения: замена листа «Отследить» из исходной таблицы."""

    year: int
    rows: list[WatchRowOut]


class PlanOverviewOut(BaseModel):
    """Год целиком: строки по категориям и три итоговых полосы."""

    year: int
    rows: list[PlanRowOut]
    income_totals: list[MonthCellOut]
    expense_totals: list[MonthCellOut]
    # Свободные средства: доходы минус расходы, по плану и по факту.
    free_totals: list[MonthCellOut]
