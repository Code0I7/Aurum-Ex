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
