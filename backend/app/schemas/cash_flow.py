from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel


class CashFlowPoint(BaseModel):
    year: int
    month: int
    income: Decimal
    expense: Decimal
    net: Decimal
    # Начальный остаток счетов, открытых в этом месяце. Уже включён в income
    # (или в expense, если остаток отрицательный) — выделен отдельно, чтобы
    # столбец «доход» в месяце открытия счёта не выглядел необъяснимым
    # всплеском.
    opening: Decimal = Decimal("0")


class DayPoint(BaseModel):
    """День месяца: сколько пришло, сколько ушло, что осталось.

    Дата целиком, а не номер дня: подпись оси, порядок и границы месяца
    тогда не надо собирать заново на той стороне.
    """

    date: date_
    income: Decimal
    expense: Decimal
    net: Decimal
    # Начальный остаток счетов, открытых в этот день. Уже включён в income
    # или в expense — см. CashFlowPoint.opening.
    opening: Decimal = Decimal("0")


class CashFlowResponse(BaseModel):
    start_date: date_ | None
    end_date: date_ | None
    points: list[CashFlowPoint]
    total_income: Decimal
    total_expense: Decimal
    total_net: Decimal
    # Сколько из оборота пришлось на начальные остатки. Ноль, если все счета
    # заведены с нуля.
    total_opening: Decimal = Decimal("0")
