from datetime import date as date_
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.text import capitalize_first_letter
from app.models.enums import SettlementKind, TransactionType
from app.schemas.account import AccountRead
from app.schemas.category import CategoryRead
from app.schemas.product import TransactionItemInput, TransactionItemRead
from app.schemas.tag import TagRead


def transfer_rule_violation(
    *,
    type: TransactionType,
    account_id: int,
    transfer_account_id: int | None,
    category_id: int | None,
) -> str | None:
    """The transfer invariants in one place, returning the problem as text or
    None if the combination is valid.

    Both halves of the write path go through this: the create schema below
    (as a pydantic validator) and the PATCH route (see
    routes/transactions.py). Enforcing it on create only used to let an edit
    produce a row that create would have rejected — most damagingly a
    transfer with no transfer_account_id, which TransactionRead itself can't
    serialize, so the row broke every later read of the transactions list.
    """
    if type == TransactionType.TRANSFER:
        if not transfer_account_id:
            return "transfer_account_id is required for transfer transactions"
        if transfer_account_id == account_id:
            return "transfer_account_id must differ from account_id"
        if category_id:
            return "category_id is not valid for transfer transactions"
    elif transfer_account_id:
        return "transfer_account_id is only valid for transfer transactions"
    return None


def split_rule_violation(
    *,
    type: TransactionType,
    amount: Decimal,
    category_id: int | None,
    split_count: int,
    split_total: Decimal | None,
) -> str | None:
    """The split invariants in one place, same shape as transfer_rule_violation
    above — checked on create, and against the row *as it would look after
    a patch* on update (see routes/transactions.py), so an edit can't leave
    a transaction whose splits no longer add up to its own amount.

    Takes counts/totals rather than the split objects themselves: the
    update path's "splits weren't touched by this patch" case has to check
    the existing ORM rows, whose category_id can be None (the category was
    since deleted) — nothing here needs a live category to check the sum.
    """
    if split_count == 0:
        return None
    if type == TransactionType.TRANSFER:
        return "splits are not valid for transfer transactions"
    if category_id is not None:
        return "category_id must be omitted when splitting a transaction across categories"
    if split_count < 2:
        return "splitting a transaction needs at least 2 categories"
    if split_total != amount:
        return f"split amounts ({split_total}) must add up to the transaction amount ({amount})"
    return None


class TransactionFields(BaseModel):
    """A transaction's shape, without the rules that only make sense while
    writing one. Reading goes through this: rows already in the database can
    stop satisfying a write-time rule through no fault of their own — the
    transfer_account_id FK is ON DELETE SET NULL, so deleting an account
    leaves the transfers that pointed at it with no destination — and
    refusing to serialize such a row would take the whole transactions list
    down with it, leaving no way in the UI to find and delete the row."""

    account_id: int
    category_id: int | None = None
    transfer_account_id: int | None = None
    type: TransactionType
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    description: str = Field(min_length=1, max_length=255)
    merchant: str | None = Field(default=None, max_length=150)
    notes: str | None = None
    date: date_

    # Валюта операции. None означает "не указана" — тогда берётся валюта
    # счёта: платёж с долларовой карты по умолчанию в долларах. Отличить
    # "не передано" от "передано RUB" на уровне модели невозможно, поэтому
    # признак живёт здесь, а не в Transaction.currency с его дефолтом.
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    # Измерения, все необязательные (см. models/transaction.py): комиссия
    # банка не относится ни к кому, у подписки нет магазина, а контрагент
    # осмыслен только для операций с внешними людьми.
    participant_id: int | None = None
    store_id: int | None = None
    counterparty_id: int | None = None
    settlement_kind: SettlementKind | None = None

    # Запись видна в истории, но в суммы и графики не входит — замена
    # самодельному обнулению количества в исходной таблице.
    is_excluded: bool = False
    # Порядок внутри дня; проставляется сервером, правится перетаскиванием.
    day_order: int = 0

    # Auto-capitalizes "траты на продукты" -> "Траты на продукты" so mixed
    # casing from quick manual entry doesn't need fixing by hand later.
    @field_validator("description")
    @classmethod
    def _capitalize_description(cls, value: str) -> str:
        return capitalize_first_letter(value)


class TransactionBase(TransactionFields):
    """The write-side shape: the fields plus the invariants a new or edited
    row has to satisfy."""

    @model_validator(mode="after")
    def _validate_type_specific_fields(self) -> "TransactionBase":
        violation = transfer_rule_violation(
            type=self.type,
            account_id=self.account_id,
            transfer_account_id=self.transfer_account_id,
            category_id=self.category_id,
        )
        if violation:
            raise ValueError(violation)
        return self


class TransactionSplitInput(BaseModel):
    category_id: int
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    note: str | None = Field(default=None, max_length=200)


class TransactionCreate(TransactionBase):
    tag_ids: list[int] = Field(default_factory=list)
    # None/omitted -> a normal single-category transaction, unchanged from
    # before. 2+ entries -> the amount is divided across categories instead
    # of using category_id (which must then be omitted — see
    # split_rule_violation). A single entry isn't accepted: that's just
    # category_id with extra steps.
    splits: list[TransactionSplitInput] | None = None
    # Позиции чека — «что лежало в пакете». Отдельно от splits и вместе с
    # ними: разбивка делит деньги по категориям и обязана сойтись с суммой,
    # позиция описывает покупку и сходиться не обязана ничему. Пустой список
    # — совершенно нормальный чек: быстрый ввод остаётся одним действием.
    items: list[TransactionItemInput] | None = None

    @model_validator(mode="after")
    def _validate_splits(self) -> "TransactionCreate":
        splits = self.splits or []
        violation = split_rule_violation(
            type=self.type,
            amount=self.amount,
            category_id=self.category_id,
            split_count=len(splits),
            split_total=sum((s.amount for s in splits), Decimal("0")) if splits else None,
        )
        if violation:
            raise ValueError(violation)
        return self


class TransactionUpdate(BaseModel):
    account_id: int | None = None
    category_id: int | None = None
    transfer_account_id: int | None = None
    type: TransactionType | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    description: str | None = Field(default=None, min_length=1, max_length=255)
    merchant: str | None = Field(default=None, max_length=150)
    notes: str | None = None
    date: date_ | None = None
    # Пропущена -> валюта не меняется; передана -> курс и сумма в базовой
    # валюте пересчитываются (см. routes/transactions.py, _apply_currency).
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    participant_id: int | None = None
    store_id: int | None = None
    counterparty_id: int | None = None
    settlement_kind: SettlementKind | None = None
    is_excluded: bool | None = None
    day_order: int | None = None
    # Omitted -> tags untouched; sent (even as []) -> replaces the full tag set.
    tag_ids: list[int] | None = None
    # Omitted -> splits untouched; sent (even as []) -> replaces the full
    # split set (send [] together with a category_id to turn a split
    # transaction back into a normal single-category one).
    splits: list[TransactionSplitInput] | None = None
    # None — позиции не трогаем; список (в том числе пустой) заменяет их
    # целиком. Правка чека — это переписывание его состава, а не дописывание
    # строк в конец.
    items: list[TransactionItemInput] | None = None

    @field_validator("description")
    @classmethod
    def _capitalize_description(cls, value: str | None) -> str | None:
        return capitalize_first_letter(value) if value is not None else None


class TransactionSplitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int | None
    category: CategoryRead | None = None
    amount: Decimal
    note: str | None


class TransactionRead(TransactionFields):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # Публичный идентификатор записи. В таблице колонка скрыта по
    # умолчанию — нужна, когда операцию надо назвать по имени вне
    # приложения (например, в отчёте об импорте).
    uuid: UUID
    account: AccountRead
    category: CategoryRead | None = None
    tags: list[TagRead] = Field(default_factory=list)
    splits: list[TransactionSplitRead] = Field(default_factory=list)
    items: list[TransactionItemRead] = Field(default_factory=list)

    # Баланс счёта после этой операции — то самое «было 0, стало 500, потом
    # 350». Заполняется только в списке (см. routes/transactions.py); у
    # одиночного ответа на создание или правку остаётся None, потому что
    # считать накопительный итог ради одной строки незачем.
    balance_after: Decimal | None = None


class TransactionReorder(BaseModel):
    """Новое место операции среди операций того же счёта за тот же день.

    Позиция, а не соседний идентификатор: интерфейс знает, куда строку
    бросили, а не между кем и кем. Выход за границы списка не ошибка — он
    зажимается к ближайшему краю, потому что бросок мимо цели не должен
    оборачиваться сообщением об ошибке."""

    position: int = Field(ge=0)


class TransactionPage(BaseModel):
    items: list[TransactionRead]
    total: int
    page: int
    page_size: int


class TransactionBulkCreate(BaseModel):
    """CSV import (see routes/transactions.py's /bulk): the frontend parses
    the file and maps its columns client-side, then sends already-shaped
    rows here. All-or-nothing — same failure semantics as backup restore, so
    a single bad row never leaves a partial import behind."""

    items: list[TransactionCreate] = Field(min_length=1, max_length=5000)


class TransactionBulkCreateResult(BaseModel):
    created: int
