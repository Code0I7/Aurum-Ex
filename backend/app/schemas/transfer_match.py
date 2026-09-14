"""Пары операций, похожие на один перевод, записанный дважды (см.
services/transfer_match_service.py)."""
from datetime import date as date_
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.models.enums import TransactionType

MatchKindName = Literal["halves", "transfer_and_in", "transfer_and_out", "transfer_twice"]


class TransferMatchSide(BaseModel):
    """Одна запись пары — ровно то, что нужно, чтобы узнать её в выписке."""

    id: int
    type: TransactionType
    date: date_
    amount: Decimal
    # Валюта операции: сумма записана в той валюте, в которой прошла.
    currency: str
    account_name: str
    # Только у перевода: куда пришло.
    transfer_account_name: str | None = None
    description: str | None = None
    category_name: str | None = None


class TransferMatchRead(BaseModel):
    kind: MatchKindName
    # Какая запись останется и какая уйдёт при склейке. Показываются обе:
    # удаляемую человек должен видеть до нажатия, а не искать после.
    keep: TransferMatchSide
    drop: TransferMatchSide


class TransferCounterpartRead(BaseModel):
    """Уже записанная операция, с которой вводимая сложилась бы в пару."""

    kind: MatchKindName
    transaction: TransferMatchSide


class TransferMatchPair(BaseModel):
    first_id: int
    second_id: int
