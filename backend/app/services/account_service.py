"""Account CRUD, plus each account's live balance — summed from its
Transaction rows (income adds, expense subtracts, a transfer moves the
amount from the source account to the destination account) rather than
stored, the same "derive it, don't duplicate it" approach
net_worth_service.py uses for Cash.
"""
from collections import defaultdict
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.enums import AccountKind, AccountNature, TransactionType
from app.models.transaction import Transaction
from app.schemas.account import AccountCreate, AccountUpdate, AccountWithBalance
from app.services.settlement_service import get_reserved_by_account
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


async def get_balances_by_account(session: AsyncSession) -> dict[int, Decimal]:
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


def _to_read(
    account: Account,
    balance: Decimal,
    balance_base: Decimal | None = None,
    reserved: Decimal = Decimal("0"),
) -> AccountWithBalance:
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
        reserved=reserved,
        # Доступно не уходит в минус: если отложено больше, чем сейчас на
        # счёте, свободных денег просто нет — но и долга это не создаёт.
        available=max(balance - reserved, Decimal("0")),
    )


async def list_accounts(session: AsyncSession, include_archived: bool) -> list[AccountWithBalance]:
    stmt = select(Account).order_by(Account.name)
    if not include_archived:
        stmt = stmt.where(Account.is_archived.is_(False))
    accounts = (await session.execute(stmt)).scalars().all()
    balances = await get_balances_by_account(session)

    # Остаток переоценивается по СЕГОДНЯШНЕМУ курсу, в отличие от операций,
    # где курс заморожен на дату. Полтинник долларов на счёте стоит столько,
    # сколько стоит сейчас, а трата 2022 года так и осталась тратой того
    # года (см. services/currency_service.py).
    rates = await get_current_rates(session)
    reserved_by_account = await get_reserved_by_account(session)

    def read(account: Account) -> AccountWithBalance:
        raw = balances.get(account.id, Decimal("0"))
        # Оба числа приводятся к двум знакам: иначе нулевой счёт отдаёт "0"
        # в одном поле и "0.00" в другом — одно и то же число в двух видах.
        return _to_read(
            account,
            quantize_money(raw),
            convert_balance(raw, account.currency, rates),
            quantize_money(reserved_by_account.get(account.id, Decimal("0"))),
        )

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


async def _refuse_currency_change(session: AsyncSession, account: Account, currency: str) -> None:
    """Валюту счёта меняют, только пока по нему нет операций.

    Баланс счёта складывается из сумм операций, а у каждой операции своя
    валюта, записанная в момент ввода. Сменить валюту счёта задним числом
    значит получить счёт, где к рублям прибавляются доллары как голые числа:
    остаток станет неправильным молча, без единой ошибки на экране.

    Пока операций нет, менять нечего и незачем запрещать: человек завёл
    карту и тут же заметил, что выбрал не ту валюту.
    """
    if currency.upper() == account.currency.upper():
        return

    used = await session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(
            or_(
                Transaction.account_id == account.id,
                Transaction.transfer_account_id == account.id,
            )
        )
    )
    if used:
        raise HTTPException(
            status_code=400,
            detail="Currency cannot change once the account has transactions",
        )


async def update_account(session: AsyncSession, account_id: int, payload: AccountUpdate) -> AccountWithBalance:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("currency"):
        await _refuse_currency_change(session, account, changes["currency"])
    # Смена вида счёта без явного указания природы переводит и природу —
    # иначе карта, ставшая кредитной, продолжила бы считаться активом.
    if "kind" in changes and "nature" not in changes:
        changes["nature"] = resolve_nature(changes["kind"], None)
    for field, value in changes.items():
        setattr(account, field, value)
    await session.commit()
    await session.refresh(account)
    balances = await get_balances_by_account(session)
    return _to_read(account, balances.get(account.id, Decimal("0")))


async def delete_account(session: AsyncSession, account_id: int) -> None:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    await session.delete(account)
    await session.commit()
