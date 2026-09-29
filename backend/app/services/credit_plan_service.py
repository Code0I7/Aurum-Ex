"""Калькулятор кредита: во что обойдётся занятая сумма.

Отвечает на вопрос, который задают перед покупкой, а не после: «если взять
сорок тысяч под 39,9% и платить минимальный платёж — сколько это выйдет».
Банк на него не отвечает: в приложении видно ежемесячный платёж, а итоговая
переплата — нет.

Считается по той же формуле аннуитета, которую банки пишут в договорах, с
месячной ставкой `годовая / 12`. Это упрощение, и оно намеренное: банк
начисляет проценты по дням, и точный счёт зависит от длины месяца, даты
выписки и дня, когда деньги дошли. Воспроизводить это здесь значило бы
обещать точность, которой нет. Расхождение с банковским числом — проценты
от суммы процентов, и на решении «брать или не брать» оно не сказывается.

Чего калькулятор не делает намеренно: не начисляет проценты на проценты
сверх обычной схемы, не знает о платах за обслуживание и снятие, не
моделирует льготный период по дням. Всё это — в условиях счёта и в
заметках к нему.
"""
from collections.abc import Callable
from decimal import ROUND_CEILING, Decimal

from app.schemas.credit import (
    CreditPlanOutcome,
    CreditPlanRequest,
    CreditPlanResponse,
    CreditPlanStep,
)

CENT = Decimal("0.01")
# Потолок на случай платежа, который почти не гасит долг: без него цикл
# крутился бы до бесконечности, а ответ «двести лет» и «никогда» для
# человека означают одно и то же.
MAX_MONTHS = 600
# Хвост, который не стоит отдельного месяца. Банки в такой ситуации делают
# последний платёж корректирующим, и по той же причине: «тринадцатый платёж
# 6 копеек» — это не график, а артефакт округления.
TAIL = Decimal("1")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT)


def _round_up(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_CEILING)


def _monthly_rate(annual_percent: Decimal) -> Decimal:
    return annual_percent / Decimal("100") / Decimal("12")


def annuity_payment(amount: Decimal, annual_percent: Decimal, months: int) -> Decimal:
    """Платёж, закрывающий сумму ровно за N месяцев.

    Формула из договоров: АП = С × ПС × (1 + ПС)ⁿ / ((1 + ПС)ⁿ − 1). При
    нулевой ставке она вырождается в деление, и делить нужно явно: возведение
    нуля в степень даёт ноль в знаменателе.
    """
    if months <= 0:
        raise ValueError("months must be positive")
    rate = _monthly_rate(annual_percent)
    if rate == 0:
        return (amount / months).quantize(Decimal("1"), rounding=ROUND_CEILING)
    factor = (Decimal("1") + rate) ** months
    # Вверх и до рубля — ровно как в договорах («округляется до целого
    # числа в большую сторону»). Округление вниз оставляло бы хвост, на
    # который приходился бы лишний платёж в тридцать копеек.
    return (amount * rate * factor / (factor - Decimal("1"))).quantize(
        Decimal("1"), rounding=ROUND_CEILING
    )


def simulate(
    amount: Decimal,
    annual_percent: Decimal,
    payment_of: Callable[[Decimal], Decimal],
) -> CreditPlanOutcome:
    """Гоняет долг по месяцам, пока он не кончится.

    `payment_of` получает остаток долга и возвращает платёж этого месяца —
    так в одном месте уживаются и минимальный платёж (доля от долга), и
    фиксированная сумма.

    Последний платёж всегда ровно закрывает остаток: платить больше долга
    банк не даст, а «переплата в 43 копейки» в расчёте выглядит ошибкой.
    """
    rate = _monthly_rate(annual_percent)
    balance = _money(amount)
    total_paid = Decimal("0")
    total_interest = Decimal("0")
    schedule: list[CreditPlanStep] = []

    for number in range(1, MAX_MONTHS + 1):
        interest = _money(balance * rate)
        payment = _money(payment_of(balance))
        due = _money(balance + interest)
        if payment >= due or due - payment <= TAIL:
            payment = due
        elif payment <= interest:
            # Долг не уменьшается — считать дальше нечего.
            return CreditPlanOutcome(
                payment=_money(payment),
                first_payment=schedule[0].payment if schedule else _money(payment),
                last_payment=_money(payment),
                months=number - 1,
                total_paid=_money(total_paid),
                total_interest=_money(total_interest),
                never_closes=True,
                schedule=schedule,
            )

        principal = _money(payment - interest)
        balance = _money(balance - principal)
        total_paid += payment
        total_interest += interest
        schedule.append(
            CreditPlanStep(
                number=number,
                payment=payment,
                interest=interest,
                principal=principal,
                balance=balance,
            )
        )
        if balance <= 0:
            break

    return CreditPlanOutcome(
        payment=schedule[0].payment if schedule else Decimal("0"),
        first_payment=schedule[0].payment if schedule else Decimal("0"),
        last_payment=schedule[-1].payment if schedule else Decimal("0"),
        months=len(schedule),
        total_paid=_money(total_paid),
        total_interest=_money(total_interest),
        never_closes=balance > 0,
        schedule=schedule,
    )


def minimum_payment_for(
    debt: Decimal, percent: Decimal | None, floor: Decimal | None
) -> Decimal | None:
    """Минимальный платёж по правилу банка: доля от долга, но не меньше порога.

    Ни доли, ни порога — правила нет, и выдумывать его нельзя: ответ
    «минимум ноль» человек прочтёт как «можно не платить».
    """
    if debt <= 0:
        return None
    if percent is None and floor is None:
        return None
    by_percent = debt * percent / Decimal("100") if percent is not None else Decimal("0")
    value = max(by_percent, floor or Decimal("0"))
    # Больше долга минимальный платёж не бывает: в последнюю выписку
    # попадает остаток, а не процент от него.
    return _money(min(value, debt))


def build_plan(payload: CreditPlanRequest) -> CreditPlanResponse:
    """Три ответа на один вопрос: минимум, разумный срок и своя сумма."""
    requested = _money(payload.amount)
    # Комиссия ложится в долг в день операции, поэтому и проценты идут уже
    # на неё. Считать её отдельным расходом было бы неверно вдвойне: она и
    # занята, и стоит процентов.
    fee = _money(
        requested * (payload.fee_percent or Decimal("0")) / Decimal("100")
        + (payload.fee_fixed or Decimal("0"))
    )
    amount = _money(requested + fee)
    rate = payload.annual_rate_percent

    minimum = None
    if payload.minimum_percent is not None or payload.minimum_floor is not None:
        def by_rule(balance: Decimal) -> Decimal:
            value = minimum_payment_for(balance, payload.minimum_percent, payload.minimum_floor)
            return value if value is not None else balance

        minimum = simulate(amount, rate, by_rule)

    recommended = None
    if payload.target_months:
        payment = annuity_payment(amount, rate, payload.target_months)
        recommended = simulate(amount, rate, lambda _balance: payment)

    fixed = None
    if payload.fixed_payment:
        fixed = simulate(amount, rate, lambda _balance: payload.fixed_payment)

    return CreditPlanResponse(
        minimum=minimum,
        recommended=recommended,
        fixed=fixed,
        in_grace=amount,
        fee=fee,
        amount_with_fee=amount,
    )
