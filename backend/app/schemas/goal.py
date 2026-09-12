from datetime import date as date_
from decimal import Decimal

from app.models.enums import GoalStatus

from pydantic import BaseModel, Field, field_validator


class GoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    target_amount: Decimal = Field(gt=0)
    # Начало накопления и планируемое завершение. Обе необязательны: цель
    # без дат — это по-прежнему цель, просто про неё нельзя сказать «идём
    # ли мы по графику».
    started_on: date_ | None = None
    planned_on: date_ | None = None
    # Счёт, на котором физически лежат отложенные деньги. Необязателен: цель
    # можно завести и до того, как решено, откуда копить. Но пока он не
    # указан, счёт не сможет показать «отложено» — деньги обещаны, а откуда
    # они возьмутся, неизвестно.
    account_id: int | None = None


class GoalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    target_amount: Decimal | None = Field(default=None, gt=0)
    started_on: date_ | None = None
    planned_on: date_ | None = None
    # Фактическая дата сбора. Приложение ставит её само в момент
    # завершения, но знает оно только день, когда нажали кнопку. Поэтому
    # поле правится руками: «собрал в июне, отметил в августе» — обычное
    # дело, и метрика «за сколько собрал» иначе врёт на два месяца.
    closed_at: date_ | None = None
    account_id: int | None = None
    # Завершение цели — ручное и намеренно не автоматическое. Накопить
    # нужную сумму и потратить её — разные события, и второе приложению
    # неоткуда узнать: деньги уходят обычной тратой, без пометок.
    #
    # ACHIEVED снимает резерв, потому что деньги уже потрачены со счёта
    # обычным расходом; вычитать их ещё раз значило бы посчитать трату
    # дважды. CANCELLED снимает резерв по другой причине — передумали, — и
    # различать их стоит: половина целей заканчивается вторым способом.
    status: GoalStatus | None = None


class GoalReservation(BaseModel):
    """Сколько этой целью отложено на конкретном счёте."""

    account_id: int
    account_name: str
    amount: Decimal


class AccountReservation(BaseModel):
    """Отрезок на полосе счёта: чем именно занята часть остатка."""

    account_id: int
    goal_id: int
    goal_name: str
    amount: Decimal


class GoalContributionCreate(BaseModel):
    # Negative allowed — a withdrawal from the goal is still a contribution
    # to its running total, just in the other direction. Zero is pointless.
    amount: Decimal
    date: date_
    note: str | None = Field(default=None, max_length=200)
    # С какого счёта откладываем (или на какой возвращаем). Необязателен:
    # цель можно вести и без привязки к счёту — тогда она остаётся планом
    # накопления и ничего не резервирует.
    account_id: int | None = None

    @field_validator("amount")
    @classmethod
    def _reject_zero(cls, value: Decimal) -> Decimal:
        # Has to be a validator: pydantic has no "not equal" constraint, so
        # the Field(ne=0) this replaces was parsed as an unknown keyword,
        # stored as schema metadata, and never actually checked anything.
        if value == 0:
            raise ValueError("amount must not be zero")
        return value


class GoalRead(BaseModel):
    id: int
    name: str
    target_amount: Decimal
    started_on: date_ | None = None
    planned_on: date_ | None = None
    # Счёт, на котором физически лежат отложенные деньги. Без него взнос
    # непонятно откуда взялся, а счёт не может показать «отложено».
    account_id: int | None = None
    status: GoalStatus = GoalStatus.ACTIVE
    # Фактическое завершение — достигнута или отменена. Пусто, пока
    # копится. Правится руками: см. GoalUpdate.
    closed_at: date_ | None = None
    current_amount: Decimal
    # Сколько всего вносили, без учёта возвратов. У завершённой цели это
    # единственное осмысленное число: перенос старой таблицы записывал
    # трату накопленного возвратом, и итог схлопывался в ноль — «накоплено
    # 0 ₽» там, где копили полгода.
    deposited: Decimal = Decimal("0")
    remaining: Decimal
    percent: float
    is_reached: bool
    # Откуда отложено. Пусто у целей без привязки к счёту.
    by_account: list[GoalReservation] = Field(default_factory=list)

    # Три числа, которые получаются из трёх дат. Считаются здесь, а не в
    # интерфейсе: правило «до какого дня считать незавершённую цель» одно,
    # и держать его в двух местах — значит однажды разойтись.
    #
    # Дней с начала накопления. У завершённой цели — до дня сбора, у
    # активной — до сегодня.
    days_saving: int | None = None
    # Дней до планируемой даты; отрицательное — просрочка. У завершённой
    # цели не считается: срок уже ни на что не влияет.
    days_to_plan: int | None = None
    # За сколько дней собрали на самом деле. Только у достигнутой цели:
    # у отменённой сбора не было.
    days_taken: int | None = None
