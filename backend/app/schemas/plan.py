"""Схемы планирования.

Сумма всегда означает одно: столько стоит одно повторение. В месяц попадает
столько, сколько повторений в него укладывается, — у ежемесячного плана это
одно, у ежедневного тридцать. Второго поля «сумма за месяц» нет намеренно:
два поля пришлось бы держать согласованными, и рано или поздно они
разошлись бы.

Проверки расписания живут в схемах на запись и только в них. PlanRead
наследует общие поля, и ограничение, попавшее в общего предка, отказывалось
бы отдавать уже сохранённую запись — а чтение и запись проверяют разное.
"""
from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import CategoryKind, PlanFrequency, PlanMonthDay


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


def _check_recurrence(plan) -> None:
    """Расписание должно означать ровно одно.

    Половина проверок здесь — про поля, которые при этой частоте ничего не
    значат: дни недели у ежемесячного плана, месяцы у недельного. Молча их
    игнорировать нельзя — человек, выбравший понедельник, ждал понедельника,
    и тихо посчитанный по другому правилу план он заметит через год, сверяя
    итоги.

    Чисел 29, 30 и 31 среди допустимых нет: «31 февраля» не существует, и
    вместо молчаливого выбора за человека есть отдельные пункты —
    «последний день месяца», «первый» и «последний рабочий день».
    """
    kind = plan.kind
    if kind is None:
        # Правка, не трогающая частоту: проверять нечего, а угадывать
        # сохранённое значение здесь не из чего.
        return

    step = plan.repeat_every if plan.repeat_every is not None else 1
    if not 1 <= step <= 365:
        raise ValueError("repeat_every must be between 1 and 365")
    if kind is PlanFrequency.ONE_OFF and step != 1:
        raise ValueError("a one-off plan does not repeat")

    if plan.weekdays is not None and (
        not plan.weekdays or any(day < 0 or day > 6 for day in plan.weekdays)
    ):
        raise ValueError("weekdays must be numbers from 0 (Monday) to 6")
    if plan.months is not None and (
        not plan.months or any(month < 1 or month > 12 for month in plan.months)
    ):
        raise ValueError("months must be numbers from 1 to 12")
    if plan.month_days is not None and (
        not plan.month_days or any(day < 1 or day > 28 for day in plan.month_days)
    ):
        raise ValueError("month_days must be numbers from 1 to 28")
    if plan.nth_weekday is not None and plan.nth_weekday not in (1, 2, 3, 4, 5, -1):
        raise ValueError("nth_weekday must be 1..5 or -1 for the last one")

    # Дни недели нужны неделе и «первому понедельнику месяца». Больше нигде
    # они ни на что не влияют.
    if plan.weekdays is not None and not (
        kind is PlanFrequency.WEEK or plan.month_day_mode is PlanMonthDay.NTH_WEEKDAY
    ):
        raise ValueError("weekdays apply to weekly plans and to the nth weekday of a month")
    if plan.month_day_mode is not None and kind not in (PlanFrequency.MONTH, PlanFrequency.YEAR):
        raise ValueError("a day within the month applies to monthly and yearly plans only")
    if plan.months is not None and kind is not PlanFrequency.YEAR:
        raise ValueError("months apply to yearly plans only")
    if plan.month_days is not None and plan.month_day_mode is not PlanMonthDay.DAY_OF_MONTH:
        raise ValueError("month_days apply to the day-of-month mode only")
    if plan.nth_weekday is not None and plan.month_day_mode is not PlanMonthDay.NTH_WEEKDAY:
        raise ValueError("nth_weekday applies to the nth-weekday mode only")
    if plan.month_day_mode is PlanMonthDay.NTH_WEEKDAY and plan.nth_weekday is None:
        raise ValueError("the nth-weekday mode needs a number")

    if plan.skip_weekends and kind is not PlanFrequency.DAY:
        raise ValueError("skipping weekends applies to daily plans only")
    # «Отработанные дни» — не календарное правило, а факт из work_periods:
    # одно число на месяц, и умножать его на шаг не на что.
    if plan.workdays_only and (kind is not PlanFrequency.DAY or step != 1):
        raise ValueError("workdays_only applies to plans repeating every day")
    # Взаимоисключающие: «отработанные дни» — факт из work_periods, «будни»
    # — календарь. Вместе они означали бы два разных числа дней на один
    # месяц, и пришлось бы выбирать молча за человека.
    if plan.workdays_only and plan.skip_weekends:
        raise ValueError("workdays_only and skipping weekends are mutually exclusive")


class PlanBase(BaseModel):
    """Поля плана без единой проверки — их наследует и PlanRead.

    Всё, что проверяет расписание, лежит в PlanCreate и PlanUpdate: схема на
    чтение обязана отдать то, что уже сохранено, даже если правила с тех пор
    ужесточились.
    """

    category_id: int | None = None
    participant_id: int | None = None
    kind: PlanFrequency
    # Шаг: «каждые N». Единица означает «каждый».
    repeat_every: int = 1
    # Дни недели, 0 — понедельник. Пусто — тот же день недели, с которого
    # план начался.
    weekdays: list[int] | None = None
    month_day_mode: PlanMonthDay | None = None
    month_days: list[int] | None = None
    # 1–5 или −1 для последнего.
    nth_weekday: int | None = None
    months: list[int] | None = None
    skip_weekends: bool = False
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    workdays_only: bool = False
    note: str | None = Field(default=None, max_length=200)
    is_active: bool = True


class PlanCreate(PlanBase):
    periods: list[PlanPeriodInput] = Field(min_length=1)

    @model_validator(mode="after")
    def check_plan(self) -> "PlanCreate":
        _check_periods(self.periods)
        _check_recurrence(self)
        return self


class PlanUpdate(BaseModel):
    category_id: int | None = None
    participant_id: int | None = None
    kind: PlanFrequency | None = None
    repeat_every: int | None = None
    weekdays: list[int] | None = None
    month_day_mode: PlanMonthDay | None = None
    month_days: list[int] | None = None
    nth_weekday: int | None = None
    months: list[int] | None = None
    skip_weekends: bool | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    # Присланный список заменяет отрезки целиком, а не дополняет их: правка
    # приходит из формы, где список виден весь, и «дополнить» означало бы,
    # что удалённую строку нельзя удалить.
    periods: list[PlanPeriodInput] | None = None
    workdays_only: bool | None = None
    note: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None

    @model_validator(mode="after")
    def check_plan(self) -> "PlanUpdate":
        if self.periods is not None:
            _check_periods(self.periods)
        _check_recurrence(self)
        return self


class PlanRead(PlanBase):
    """Сохранённый план. Проверок расписания здесь нет намеренно — см.
    PlanBase: отдать надо то, что лежит в базе."""

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
