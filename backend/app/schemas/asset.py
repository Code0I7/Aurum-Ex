from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AssetClass, CapitalRole, RiskLevel


class AssetValuationCreate(BaseModel):
    value: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    as_of_date: date_ = Field(default_factory=date_.today)


class AssetValuationUpdate(BaseModel):
    """Правка записанной оценки: опечатка в цене или в дате.

    Оба поля необязательны — правят обычно что-то одно.
    """

    value: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    as_of_date: date_ | None = None


class AssetValuationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    value: Decimal
    as_of_date: date_


class AssetBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    asset_class: AssetClass
    # Пусто — валюта установки: её подставляет маршрут, как и у счёта.
    # Раньше здесь стоял доллар, и на рублёвой установке новый актив
    # оказывался долларовым, а в рублёвый капитал не попадал вовсе.
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notes: str | None = None
    capital_role: CapitalRole = CapitalRole.NEUTRAL
    # Rough self-reported monthly net cash flow — informational, not tracked
    # transactions (see Asset.monthly_cash_flow).
    monthly_cash_flow: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    # Квартира, в которой живут, и машина, на которой ездят. По умолчанию
    # не входят в главную цифру капитала: шесть миллионов, из которых 5,8
    # — жильё, которое не продадут, — число, на которое нельзя опереться.
    is_personal_use: bool = False


class AssetCreate(AssetBase):
    value: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    as_of_date: date_ = Field(default_factory=date_.today)


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    asset_class: AssetClass | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notes: str | None = None
    capital_role: CapitalRole | None = None
    monthly_cash_flow: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    risk_level: RiskLevel | None = None
    is_personal_use: bool | None = None


class AssetRead(AssetBase):
    model_config = ConfigDict(from_attributes=True)

    # У записанного актива валюта есть всегда: в ответе она не пустая.
    currency: str
    id: int
    current_value: Decimal
    as_of_date: date_
