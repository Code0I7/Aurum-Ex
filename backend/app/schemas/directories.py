"""Схемы справочников: участники, магазины, контрагенты.

Банки описаны в schemas/account.py — они там нужны вложенными в счёт, и
разносить их пришлось бы через импорт по кругу.
"""
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


class StoreBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    location: str | None = Field(default=None, max_length=200)
    notes: str | None = None


class StoreCreate(StoreBase):
    pass


class StoreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    location: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    is_archived: bool | None = None


class StoreRead(StoreBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_archived: bool


class CounterpartyBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    notes: str | None = None


class CounterpartyCreate(CounterpartyBase):
    pass


class CounterpartyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    notes: str | None = None
    is_archived: bool | None = None


class CounterpartyRead(CounterpartyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_archived: bool
