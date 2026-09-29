"""Схемы условий по кредиту.

Ставка хранится и передаётся так, как её называет банк: 24.9 — это 24.9, а
не 0.249. Значение должно сверяться глазами с договором без пересчёта в
уме, иначе ошибка в сто раз останется незамеченной.
"""
from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CreditRateWrite(BaseModel):
    """Строка матрицы ставок: что за операция, под сколько и когда."""

    name: str = Field(min_length=1, max_length=120)
    percent: Decimal = Field(ge=0, le=1000)
    condition: str | None = Field(default=None, max_length=200)


class CreditRateRead(CreditRateWrite):
    model_config = ConfigDict(from_attributes=True)

    id: int


class CreditTermsWrite(BaseModel):
    annual_rate_percent: Decimal | None = Field(default=None, ge=0, le=1000)
    credit_limit: Decimal | None = Field(default=None, ge=0)
    # Беспроцентный период: 120 дней у рассрочки, 55 у типичной карты.
    grace_days: int | None = Field(default=None, ge=0, le=1000)
    # День месяца, когда банк ждёт платёж. 31 допустим: в коротком месяце он
    # прижимается к последнему дню (см. credit_service.next_payment_date).
    payment_day: int | None = Field(default=None, ge=1, le=31)
    # Минимальный платёж: порог в деньгах и доля от долга. Банк задаёт его
    # правилом — «не более 8% от задолженности, минимум 600 рублей», — и
    # одно фиксированное число устаревает в первый же месяц.
    minimum_payment: Decimal | None = Field(default=None, ge=0)
    minimum_payment_percent: Decimal | None = Field(default=None, ge=0, le=100)
    opened_on: date_ | None = None
    closes_on: date_ | None = None
    notes: str | None = Field(default=None, max_length=2000)
    # Пусто и отсутствие поля — разные вещи: пустой список стирает матрицу,
    # непереданное поле оставляет её как была.
    rates: list[CreditRateWrite] | None = None


class CreditTermsRead(CreditTermsWrite):
    account_id: int
    account_name: str
    # Валюта счёта. Долг по долларовой карте — это доллары, и подписывать
    # его значком валюты установки значит называть сумму неверно.
    account_currency: str = ""
    # Долг положительным числом: баланс счёта отрицателен, но «должен 12 300»
    # читается легче, чем «баланс −12 300».
    debt: Decimal
    # Производное от лимита и долга. None, когда лимит не задан: у обычного
    # кредита его нет, и показывать «доступно 0» было бы неправдой.
    available: Decimal | None = None
    used_percent: float | None = None
    # Оценка, а не банковское число: льготный период и точный счёт дней здесь
    # не воспроизводятся.
    estimated_monthly_interest: Decimal | None = None
    # Минимальный платёж от текущего долга: max(процент × долг, порог). Тоже
    # оценка — банк считает его на дату выписки, а не на сегодня.
    minimum_payment_due: Decimal | None = None
    rates: list[CreditRateRead] = []


class CreditSummary(BaseModel):
    """Итог для карточки долгов."""

    debt: Decimal
    estimated_monthly_interest: Decimal


class CreditPlanRequest(BaseModel):
    """Вопрос калькулятора: «взял столько-то — что будет дальше».

    Ничего не сохраняет и ни к какому счёту не привязан: считать хочется и
    до того, как карта заведена в приложении.
    """

    amount: Decimal = Field(gt=0, le=Decimal("1000000000"))
    annual_rate_percent: Decimal = Field(ge=0, le=1000)
    minimum_percent: Decimal | None = Field(default=None, ge=0, le=100)
    minimum_floor: Decimal | None = Field(default=None, ge=0)
    # Платёж, который человек назначил себе сам.
    fixed_payment: Decimal | None = Field(default=None, gt=0)
    # За сколько месяцев хочется закрыть. По нему считается рекомендуемый
    # платёж.
    target_months: int | None = Field(default=None, ge=1, le=600)
    # Плата за саму операцию: «2,9% плюс 290 ₽» за снятие наличных или
    # перевод за пределы банка. Ложится в долг в день операции, поэтому
    # проценты идут уже и на неё.
    fee_percent: Decimal | None = Field(default=None, ge=0, le=100)
    fee_fixed: Decimal | None = Field(default=None, ge=0)


class CreditPlanStep(BaseModel):
    number: int
    payment: Decimal
    interest: Decimal
    principal: Decimal
    balance: Decimal


class CreditPlanOutcome(BaseModel):
    """Чем кончится, если платить так."""

    payment: Decimal
    first_payment: Decimal
    last_payment: Decimal
    months: int
    total_paid: Decimal
    total_interest: Decimal
    # Долг не уменьшается: платёж не покрывает даже процентов. Расчёт в
    # таком случае оборван, и молчать об этом нельзя.
    never_closes: bool = False
    schedule: list[CreditPlanStep] = []


class CreditPlanResponse(BaseModel):
    minimum: CreditPlanOutcome | None = None
    recommended: CreditPlanOutcome | None = None
    fixed: CreditPlanOutcome | None = None
    # Сколько стоит закрыть всё сразу в льготный период — ноль процентов и
    # один платёж. Ради сравнения: остальные числа без него выглядят
    # неизбежными. Комиссия входит и сюда: её платят в любом случае.
    in_grace: Decimal
    # Плата за операцию и долг вместе с ней. Показываются отдельно, потому
    # что «взял 127 000, должен 129 523» — это не опечатка, а комиссия.
    fee: Decimal = Decimal("0")
    amount_with_fee: Decimal
