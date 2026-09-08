"""Схемы инвестиций.

Количество и стоимость владения нигде не хранятся — они пересчитываются из
журнала сделок при каждом чтении. Та же форма «записываем факт, остальное
выводим», что у остатков на счетах и у целей: хранимый итог — это второй
источник истины, и он расходится с журналом при первой же правке сделки.
"""
from datetime import date as date_
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import InvestmentKind, RiskLevel, TradeSide


class PortfolioBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    is_archived: bool = False


class PortfolioCreate(PortfolioBase):
    pass


class PortfolioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    is_archived: bool | None = None


class PortfolioRead(PortfolioBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    holdings: int = 0
    value: Decimal = Decimal("0")
    cost_basis: Decimal = Decimal("0")


class HoldingBase(BaseModel):
    portfolio_id: int
    name: str = Field(min_length=1, max_length=150)
    ticker: str | None = Field(default=None, max_length=30)
    kind: InvestmentKind
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    external_id: str | None = Field(default=None, max_length=100)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    notes: str | None = None
    is_archived: bool = False


class HoldingCreate(HoldingBase):
    pass


class HoldingUpdate(BaseModel):
    portfolio_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=150)
    ticker: str | None = Field(default=None, max_length=30)
    kind: InvestmentKind | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    external_id: str | None = Field(default=None, max_length=100)
    last_price: Decimal | None = Field(default=None, ge=0)
    risk_level: RiskLevel | None = None
    notes: str | None = None
    is_archived: bool | None = None


class HoldingRead(HoldingBase):
    id: int
    last_price: Decimal | None = None
    last_price_at: datetime | None = None

    # Выведено из журнала, не хранится.
    quantity: Decimal = Decimal("0")
    # Во сколько обошлось то, что ещё на руках. Не то же, что вложено: часть
    # вложенного уже продана.
    cost_basis: Decimal = Decimal("0")
    invested: Decimal = Decimal("0")
    average_cost: Decimal | None = None
    # Текущая стоимость. None, когда цена не известна: показать ноль значило
    # бы объявить актив обесценившимся.
    value: Decimal | None = None
    # Бумажная прибыль — то, что будет, если продать сейчас.
    unrealised: Decimal | None = None
    unrealised_percent: float | None = None
    # Зафиксированная прибыль — то, что уже случилось и не изменится.
    realised: Decimal = Decimal("0")
    # Продано больше, чем куплено: не ошибка расчёта, а пропуск в данных.
    oversold: Decimal = Decimal("0")
    trades: int = 0


class TradeBase(BaseModel):
    side: TradeSide
    quantity: Decimal = Field(gt=0, max_digits=28, decimal_places=8)
    price_per_unit: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    fee: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    trade_date: date_
    account_id: int | None = None
    note: str | None = Field(default=None, max_length=200)


class TradeCreate(TradeBase):
    pass


class TradeUpdate(BaseModel):
    side: TradeSide | None = None
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=28, decimal_places=8)
    price_per_unit: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=8)
    fee: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    trade_date: date_ | None = None
    account_id: int | None = None
    note: str | None = Field(default=None, max_length=200)


class TradeRead(TradeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    holding_id: int
    day_order: int


class DisposalLot(BaseModel):
    """Какая партия и в каком объёме ушла в эту продажу."""

    quantity: Decimal
    cost_per_unit: Decimal
    acquired_on: date_ | None


class DisposalRead(BaseModel):
    """Одна продажа, разнесённая по партиям.

    Показывает, из чего именно списали: «продали то, что купили в мае
    2022-го». Средневзвешенная такого ответа дать не могла в принципе.
    """

    trade_id: int
    trade_date: date_
    quantity: Decimal
    proceeds: Decimal
    cost: Decimal
    realised: Decimal
    lots: list[DisposalLot]


class HoldingDetail(HoldingRead):
    """Позиция вместе с открытыми партиями и историей фиксаций."""

    open_lots: list[DisposalLot] = []
    disposals: list[DisposalRead] = []
