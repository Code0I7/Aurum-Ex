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


class PlanPeriodInput(BaseModel):
    """Сумма плана на отрезке времени.

    Отрезков у плана может быть несколько: тариф меняется, а категория и
    способ счёта остаются теми же. Заметка отвечает на вопрос «почему тут
    другое число» — через год его не вспомнит никто.
    """

    amount: Decimal = Field(gt=0)
    valid_from: date_
    valid_to: date_ | None = None
    note: str | None = Field(default=None, max_length=200)
    # Только про показ в форме: на расчёт не влияет.
    is_archived: bool = False

    @model_validator(mode="after")
    def check_order(self) -> "PlanPeriodInput":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not be earlier than valid_from")
        return self


class PlanPeriodRead(PlanPeriodInput):
    id: int

    model_config = {"from_attributes": True}


def _check_periods(periods: list[PlanPeriodInput]) -> None:
    """Отрезки не должны перекрываться.

    На один месяц приложение обязано знать одну сумму. Выбирать за человека,
    какая из двух главнее, значило бы врать в таблице года — причём молча и
    правдоподобно.

    Открытый конец (valid_to пустая) считается уходящим в бесконечность,
    поэтому такой отрезок может быть только последним.
    """
    if not periods:
        raise ValueError("a plan needs at least one period")

    ordered = sorted(periods, key=lambda period: period.valid_from)
    for earlier, later in zip(ordered, ordered[1:]):
        if earlier.valid_to is None or earlier.valid_to >= later.valid_from:
            raise ValueError("plan periods must not overlap")


class PlanBase(BaseModel):
    category_id: int | None = None
    participant_id: int | None = None
    kind: PlanKind
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    workdays_only: bool = False
    weekdays_only: bool = False
    note: str | None = Field(default=None, max_length=200)
    is_active: bool = True

    @model_validator(mode="after")
    def check_period(self) -> "PlanBase":
        # Признак «только рабочие дни» имеет смысл лишь у ежедневного плана.
        # Молча его игнорировать нельзя: человек, поставивший галочку на
        # ежемесячном плане, ждал другого поведения.
        if self.workdays_only and self.kind is not PlanKind.DAILY:
            raise ValueError("workdays_only applies to daily plans only")
        if self.weekdays_only and self.kind is not PlanKind.DAILY:
            raise ValueError("weekdays_only applies to daily plans only")
        # Взаимоисключающие: «отработанные дни» — факт из work_periods,
        # «будни» — календарь. Вместе они означали бы два разных числа дней
        # на один месяц, и пришлось бы выбирать молча за человека.
        if self.workdays_only and self.weekdays_only:
            raise ValueError("workdays_only and weekdays_only are mutually exclusive")
        return self


class PlanCreate(PlanBase):
    periods: list[PlanPeriodInput] = Field(min_length=1)

    @model_validator(mode="after")
    def check_periods(self) -> "PlanCreate":
        _check_periods(self.periods)
        return self


class PlanUpdate(BaseModel):
    category_id: int | None = None
    participant_id: int | None = None
    kind: PlanKind | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    # Присланный список заменяет отрезки целиком, а не дополняет их: правка
    # приходит из формы, где список виден весь, и «дополнить» означало бы,
    # что удалённую строку нельзя удалить.
    periods: list[PlanPeriodInput] | None = None
    workdays_only: bool | None = None
    weekdays_only: bool | None = None
    note: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None

    @model_validator(mode="after")
    def check_periods(self) -> "PlanUpdate":
        if self.periods is not None:
            _check_periods(self.periods)
        return self


class PlanRead(PlanBase):
    id: int
    periods: list[PlanPeriodRead] = []
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
    # «Зарплата · Иван» — путь до корня ветки, для подсказки при
    # наведении: имена подкатегорий не уникальны.
    path: str
    # Глубина в дереве: 0 — корень. По ней рисуется отступ.
    depth: int
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
