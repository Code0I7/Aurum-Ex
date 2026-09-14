"""Перевод между своими счетами, записанный дважды: список пар, проверка
перед записью, склейка и отказ (см. services/transfer_match_service.py).

Свой файл, а не ещё четыре маршрута в transactions.py: там и так больше
восьмисот строк, а здесь отдельная задача со своими правилами.
"""
from datetime import date as date_
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_session
from app.models.account import Account
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.schemas.transfer_match import (
    TransferCounterpartRead,
    TransferMatchPair,
    TransferMatchRead,
    TransferMatchSide,
)
from app.services.transfer_match_service import (
    Movement,
    dismiss_match,
    find_counterparts,
    find_matches,
    merge_match,
)

router = APIRouter(prefix="/transactions/transfer-matches", tags=["transactions"])


async def _sides(session: AsyncSession, ids: set[int]) -> dict[int, TransferMatchSide]:
    """Записи пар одним запросом, со счетами и категорией."""
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(Transaction)
            .options(
                selectinload(Transaction.account),
                selectinload(Transaction.transfer_account),
                selectinload(Transaction.category),
            )
            .where(Transaction.id.in_(ids))
        )
    ).scalars()
    return {
        row.id: TransferMatchSide(
            id=row.id,
            type=row.type,
            date=row.date,
            amount=row.amount,
            currency=row.currency,
            account_name=row.account.name if row.account else "—",
            transfer_account_name=row.transfer_account.name if row.transfer_account else None,
            description=row.description,
            category_name=row.category.name if row.category else None,
        )
        for row in rows
    }


@router.get("", response_model=list[TransferMatchRead])
async def read_transfer_matches(session: AsyncSession = Depends(get_session)) -> list[TransferMatchRead]:
    """Пары, похожие на один перевод, записанный дважды. Новые сверху: их
    человек помнит и разберёт быстрее."""
    matches = await find_matches(session)
    sides = await _sides(session, {match.keep_id for match in matches} | {match.drop_id for match in matches})
    result = [
        TransferMatchRead(kind=match.kind.value, keep=sides[match.keep_id], drop=sides[match.drop_id])
        for match in matches
        if match.keep_id in sides and match.drop_id in sides
    ]
    result.sort(key=lambda item: (max(item.keep.date, item.drop.date), item.keep.id), reverse=True)
    return result


@router.get("/check", response_model=list[TransferCounterpartRead])
async def check_transfer_match(
    type: TransactionType = Query(...),
    account_id: int = Query(...),
    amount: Decimal = Query(..., gt=0),
    date: date_ = Query(...),
    transfer_account_id: int | None = Query(default=None),
    transfer_amount: Decimal | None = Query(default=None, gt=0),
    session: AsyncSession = Depends(get_session),
) -> list[TransferCounterpartRead]:
    """Сложилась бы вводимая операция в пару с уже записанной.

    Отдельным запросом перед записью, а не отказом при самой записи — по
    той же причине, что и у проверки повторов дня: импорт и регулярные
    платежи законно пишут такие операции, а переспрашивать имеет смысл
    только того, кто вводит руками.
    """
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    transfer_currency: str | None = None
    if type is TransactionType.TRANSFER and transfer_account_id is not None:
        destination = await session.get(Account, transfer_account_id)
        if destination is not None and destination.currency.upper() != account.currency.upper():
            transfer_currency = destination.currency
        else:
            # Одна валюта — второй суммы нет, как и в самой операции.
            transfer_amount = None
    else:
        transfer_account_id = None
        transfer_amount = None

    draft = Movement(
        id=0,
        type=type,
        date=date,
        account_id=account_id,
        transfer_account_id=transfer_account_id,
        amount=amount,
        currency=account.currency,
        transfer_amount=transfer_amount,
        transfer_currency=transfer_currency if transfer_amount is not None else None,
    )
    found = await find_counterparts(session, draft)
    sides = await _sides(session, {transaction_id for _, transaction_id in found})
    return [
        TransferCounterpartRead(kind=kind.value, transaction=sides[transaction_id])
        for kind, transaction_id in found
        if transaction_id in sides
    ]


@router.post("/merge")
async def merge_transfer_match(
    payload: TransferMatchPair, session: AsyncSession = Depends(get_session)
) -> dict[str, int]:
    kept_id = await merge_match(session, payload.first_id, payload.second_id)
    return {"kept_id": kept_id}


@router.post("/dismiss", status_code=204)
async def dismiss_transfer_match(
    payload: TransferMatchPair, session: AsyncSession = Depends(get_session)
) -> None:
    await dismiss_match(session, payload.first_id, payload.second_id)
