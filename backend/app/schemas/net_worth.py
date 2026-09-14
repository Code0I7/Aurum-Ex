from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, Field


class NetWorthPoint(BaseModel):
    date: date_
    value: Decimal


class NetWorthBreakdownItem(BaseModel):
    key: str
    name: str
    color: str
    icon: str
    amount: Decimal
    percent: float


class CapitalRoleSummary(BaseModel):
    """Assets grouped by how they behave month to month (see CapitalRole) —
    a cross-cut of the asset-class breakdown, not a replacement for it."""

    role: str
    label: str
    color: str
    total_value: Decimal
    monthly_cash_flow: Decimal
    count: int


class RiskLevelItem(BaseModel):
    """One holding within a risk tier — Cash (key="cash") or a single asset
    (key=f"asset:{id}"). This list IS the diversification view: a tier with
    one item at 100% is concentrated, several items with even shares aren't,
    no separate score needed."""

    key: str
    name: str
    amount: Decimal
    percent: float  # share of this tier, not of total capital


class RiskLevelSummary(BaseModel):
    """Cash + assets grouped by user-tagged risk of loss (see RiskLevel) —
    another cross-cut, like capital_roles, but Cash participates here since
    it's the zero-risk anchor an 80/20-style allocation rule needs."""

    risk_level: str
    label: str
    color: str
    total_value: Decimal
    percent: float  # share of total capital (cash + assets)
    items: list[RiskLevelItem]


class NetWorthSummary(BaseModel):
    """Капитал: одна кривая и несколько срезов.

    Итог намеренно разложен на три числа, а не сведён к одному.

    * `current` — всё вместе: деньги, вложения, имущество, минус долги. На
      вопрос «сколько я стою» отвечает оно.
    * `liquid` — то, что можно потратить завтра: деньги на счетах и
      наличные за вычетом долга по картам. Акции и крипта сюда не входят —
      они капитал, но не быстрые деньги; квартира тем более.
    * `personal_use` — жильё, в котором живут, и машина, на которой ездят.
      Часть капитала, но такая, которой нельзя воспользоваться, не изменив
      жизнь целиком.

    Свести это к одному числу было бы удобнее ровно до первого решения,
    которое на него опирают. Шесть миллионов, из которых 5,8 — квартира,
    не отвечают ни на «могу ли я это купить», ни на «хватит ли мне до
    зарплаты».
    """

    range: str
    # В какой валюте посчитан этот ответ и какие ещё есть на выбор.
    # Капитал — состояние, и переводить его нельзя: сто евро на евровой
    # карте это сто евро, а не их сегодняшняя цена в рублях. Поэтому не
    # один пересчитанный итог, а по величине на валюту, и переключатель
    # между ними.
    currency: str = ""
    currencies: list[str] = Field(default_factory=list)
    current: Decimal
    # Всё, что лежит вне выбранной валюты, — приведённое к валюте
    # установки по СЕГОДНЯШНЕМУ курсу. Единственное переведённое число
    # здесь, и переведено оно потому, что иначе его не выразить: евро с
    # юанями не складываются. Отсюда же и «примерно» рядом с ним в
    # интерфейсе.
    other_base: Decimal = Decimal("0")
    # Итог одной цифрой: выбранная валюта плюс всё остальное, в валюте
    # установки. Тоже оценка, и по той же причине.
    total_base: Decimal = Decimal("0")
    # Быстрые деньги: счета и наличные минус долг по картам.
    liquid: Decimal = Decimal("0")
    # Имущество личного пользования — входит в current, но отдельной строкой.
    personal_use: Decimal = Decimal("0")
    # Долг по кредиткам и рассрочкам — положительным числом, «сколько
    # должен». Уже вычтен из current и liquid; отдельно нужен затем, чтобы
    # итог не выглядел загадкой: 72 тысячи, когда на счетах 127, объясняются
    # ровно этой строкой.
    liabilities: Decimal = Decimal("0")
    change_amount: Decimal
    change_percent: float | None
    series: list[NetWorthPoint]
    breakdown: list[NetWorthBreakdownItem]
    capital_roles: list[CapitalRoleSummary]
    risk_levels: list[RiskLevelSummary]
