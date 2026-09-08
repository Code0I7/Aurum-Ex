"""Account CRUD, plus each account's live balance — summed from its
Transaction rows (income adds, expense subtracts, a transfer moves the
amount from the source account to the destination account) rather than
stored, the same "derive it, don't duplicate it" approach
net_worth_service.py uses for Cash.
"""
from collections import defaultdict
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.enums import AccountKind, AccountNature, TransactionType
from app.models.transaction import Transaction
from app.schemas.account import AccountCreate, AccountUpdate, AccountWithBalance
from app.services.currency_service import (
    convert_balance,
    get_base_currency,
    get_current_rates,
    quantize_money,
)

# Kinds whose balance is a debt rather than savings. Used only to pick a
# default when the user doesn't state a nature — the stored value always
# wins afterwards, because an account's nature can legitimately differ from
# what its kind suggests (a store instalment account is OTHER by kind).
_LIABILITY_KINDS = {AccountKind.CREDIT_CARD, AccountKind.LOAN}


async def _account_balances(session: AsyncSession) -> dict[int, Decimal]:
    """Опорная точка баланса — начальный остаток счёта, а не ноль: деньги,
    лежавшие на счёте до первой записи, входят в баланс, но доходом не
    являются (см. models/account.py). Формула — "начальный остаток плюс
    заработано минус потрачено".

    Именно это слагаемое обычно отсутствует в самодельных таблицах: класть
    деньги на счёт там можно только операцией, а операция бывает лишь
    доходом или расходом. Отсюда стартовый остаток, проведённый доходом, и
    завышенный заработок за первый год учёта."""
    opening_result = await session.execute(select(Account.id, Account.opening_balance))
    balances: dict[int, Decimal] = defaultdict(Decimal)
    for account_id, opening_balance in opening_result.all():
        balances[account_id] = opening_balance or Decimal("0")

    result = await session.execute(
        select(
            Transaction.type,
            Transaction.amount,
            Transaction.account_id,
            Transaction.transfer_account_id,
            Transaction.is_excluded,
        )
    )
    for tx_type, amount, account_id, transfer_account_id, is_excluded in result.all():
        # Записи, помеченные "не учитывать", видны в истории, но на деньги
        # не влияют — возвращённый товар, отменённая операция.
        if is_excluded:
            continue
        # EXTERNAL_IN/OUT двигают баланс так же, как доход и расход: разница
        # только в том, что они не попадают в заработок (см. TransactionType).
        if tx_type in (TransactionType.INCOME, TransactionType.EXTERNAL_IN):
            balances[account_id] += amount
        elif tx_type in (TransactionType.EXPENSE, TransactionType.EXTERNAL_OUT):
            balances[account_id] -= amount
        elif tx_type == TransactionType.TRANSFER:
            balances[account_id] -= amount
            if transfer_account_id is not None:
                balances[transfer_account_id] += amount
    return balances


def resolve_nature(kind: AccountKind, explicit: AccountNature | None) -> AccountNature:
    """Природа счёта, заданная пользователем, либо выведенная из вида."""
    if explicit is not None:
        return explicit
    return AccountNature.LIABILITY if kind in _LIABILITY_KINDS else AccountNature.ASSET


def _to_read(account: Account, balance: Decimal, balance_base: Decimal | None = None) -> AccountWithBalance:
    return AccountWithBalance(
        id=account.id,
        name=account.name,
        kind=account.kind,
        nature=account.nature,
        bank_id=account.bank_id,
        currency=account.currency,
        opening_balance=account.opening_balance,
        opening_date=account.opening_date,
        allow_negative=account.allow_negative,
        color=account.color,
        is_archived=account.is_archived,
        balance=balance,
        balance_base=balance_base if balance_base is not None else balance,
    )


async def list_accounts(session: AsyncSession, include_archived: bool) -> list[AccountWithBalance]:
    stmt = select(Account).order_by(Account.name)
    if not include_archived:
        stmt = stmt.where(Account.is_archived.is_(False))
    accounts = (await session.execute(stmt)).scalars().all()
    balances = await _account_balances(session)

    # Остаток переоценивается по СЕГОДНЯШНЕМУ курсу, в отличие от операций,
    # где курс заморожен на дату. Полтинник долларов на счёте стоит столько,
    # сколько стоит сейчас, а трата 2022 года так и осталась тратой того
    # года (см. services/currency_service.py).
    rates = await get_current_rates(session)

    def read(account: Account) -> AccountWithBalance:
        raw = balances.get(account.id, Decimal("0"))
        # Оба числа приводятся к двум знакам: иначе нулевой счёт отдаёт "0"
        # в одном поле и "0.00" в другом — одно и то же число в двух видах.
        return _to_read(account, quantize_money(raw), convert_balance(raw, account.currency, rates))

    return [read(account) for account in accounts]


async def create_account(session: AsyncSession, payload: AccountCreate) -> AccountWithBalance:
    data = payload.model_dump()
    # Валюта не указана — берём базовую из настроек приложения, а не из
    # литерала в схеме: её выбирает пользователь.
    if not data.get("currency"):
        data["currency"] = await get_base_currency(session)
    # Природа и разрешение уходить в минус выводятся из вида счёта, если
    # пользователь не задал их явно: дебетовая карта уйти в минус не может,
    # кредитная — только так и живёт.
    nature = resolve_nature(payload.kind, payload.nature)
    data["nature"] = nature
    if payload.allow_negative is None:
        data["allow_negative"] = nature is AccountNature.LIABILITY
    account = Account(**data)
    session.add(account)
    await session.commit()
    await session.refresh(account)
    # A brand-new account has only its opening balance — no need to query.
    return _to_read(account, account.opening_balance or Decimal("0"))


async def update_account(session: AsyncSession, account_id: int, payload: AccountUpdate) -> AccountWithBalance:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    changes = payload.model_dump(exclude_unset=True)
    # Смена вида счёта без явного указания природы переводит и природу —
    # иначе карта, ставшая кредитной, продолжила бы считаться активом.
    if "kind" in changes and "nature" not in changes:
        changes["nature"] = resolve_nature(changes["kind"], None)
    for field, value in changes.items():
        setattr(account, field, value)
    await session.commit()
    await session.refresh(account)
    balances = await _account_balances(session)
    return _to_read(account, balances.get(account.id, Decimal("0")))


async def delete_account(session: AsyncSession, account_id: int) -> None:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    await session.delete(account)
    await session.commit()
