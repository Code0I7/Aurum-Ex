"""Схемы справочников: участники, магазины, контрагенты.

Банки описаны в schemas/account.py — они там нужны вложенными в счёт, и
разносить их пришлось бы через импорт по кругу.
"""
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ParticipantKind


class ParticipantBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: ParticipantKind = ParticipantKind.PERSON
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class ParticipantCreate(ParticipantBase):
    pass


class ParticipantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    kind: ParticipantKind | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    is_archived: bool | None = None


class ParticipantRead(ParticipantBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_archived: bool
    # Сколько операций ссылается на запись. Нужно, чтобы удаление не было
    # вслепую: две почти одинаковые строки в списке выглядят одинаково,
    # а стоят за ними триста покупок и ноль.
    usage: int = 0

class StoreBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    location: str | None = Field(default=None, max_length=200)
    # Полка на странице справочников. Ни на что, кроме показа, не влияет.
    group_name: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class StoreCreate(StoreBase):
    pass


class StoreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    location: str | None = Field(default=None, max_length=200)
    group_name: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    is_archived: bool | None = None


class StoreRead(StoreBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_archived: bool
    # Сколько операций ссылается на запись. Нужно, чтобы удаление не было
    # вслепую: две почти одинаковые строки в списке выглядят одинаково,
    # а стоят за ними триста покупок и ноль.
    usage: int = 0
    # Сколько денег ушло в этот магазин: за всё время и за скользящий год.
    #
    # Число покупок рядом ничего не объясняет: сорок заходов в булочную и
    # четыре заказа на маркетплейсе выглядят так, будто дело в булочной.
    # Суммы переворачивают картину — ради этого столбец и нужен.
    spent_total: Decimal = Decimal("0")
    spent_year: Decimal = Decimal("0")

class CounterpartyBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    # Полка на странице справочников. Ни на что, кроме показа, не влияет.
    group_name: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class CounterpartyCreate(CounterpartyBase):
    pass


class CounterpartyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    group_name: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    is_archived: bool | None = None


class CounterpartyRead(CounterpartyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_archived: bool
    # Сколько операций ссылается на запись. Нужно, чтобы удаление не было
    # вслепую: две почти одинаковые строки в списке выглядят одинаково,
    # а стоят за ними триста покупок и ноль.
    usage: int = 0