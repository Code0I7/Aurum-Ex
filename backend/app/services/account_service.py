"""Account CRUD, plus each account's live balance — summed from its
Transaction rows (income adds, expense subtracts, a transfer moves the
amount from the source account to the destination account) rather than
stored, the same "derive it, don't duplicate it" approach
net_worth_service.py uses for Cash.
"""
from collections import defaultdict
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
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
    to_base,
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
            # Сколько пришло на счёт получателя. Пусто у перевода внутри
            # одной валюты — там это ровно та же сумма.
            Transaction.transfer_amount,
        )
    )
    for (
        tx_type,
        amount,
        account_id,
        transfer_account_id,
        is_excluded,
        transfer_amount,
    ) in result.all():
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
                # Между валютами уходит одно, приходит другое: сто евро с
                # евровой карты превращаются в те рубли, которые дал банк.
                # Прибавить сюда отправленную сумму значило бы записать на
                # рублёвую карту сто рублей.
                balances[transfer_account_id] += (
                    transfer_amount if transfer_amount is not None else amount
                )
    return balances


def resolve_nature(kind: AccountKind, explicit: AccountNature | None) -> AccountNature:
    """Природа счёта, заданная пользователем, либо выведенная из вида."""
    if explicit is not None:
        return explicit
    return AccountNature.LIABILITY if kind in _LIABILITY_KINDS else AccountNature.ASSET


async def count_transactions_by_account(session: AsyncSession) -> dict[int, int]:
    """Сколько операций записано на каждый счёт.

    Нужно форме счёта: при смене валюты она говорит, сколько записей будет
    пересчитано, а «47 операций» человек читает совсем иначе, чем «все
    операции».

    Считаются только те, чья колонка счёта указывает сюда. Перевод
    записывается один раз, со стороны отправителя: у получателя он есть в
    балансе, но своей строки там нет — и валюту эта строка несёт чужую.
    """
    rows = await session.execute(
        select(Transaction.account_id, func.count()).group_by(Transaction.account_id)
    )
    return {account_id: count for account_id, count in rows.all()}


def _to_read(
    account: Account,
    balance: Decimal,
    balance_base: Decimal | None = None,
    reserved: Decimal = Decimal("0"),
    transaction_count: int = 0,
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
        transaction_count=transaction_count,
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
    counts = await count_transactions_by_account(session)

    def read(account: Account) -> AccountWithBalance:
        raw = balances.get(account.id, Decimal("0"))
        # Оба числа приводятся к двум знакам: иначе нулевой счёт отдаёт "0"
        # в одном поле и "0.00" в другом — одно и то же число в двух видах.
        return _to_read(
            account,
            quantize_money(raw),
            convert_balance(raw, account.currency, rates),
            quantize_money(reserved_by_account.get(account.id, Decimal("0"))),
            counts.get(account.id, 0),
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


async def _change_currency(session: AsyncSession, account: Account, currency: str) -> None:
    """Меняет валюту счёта вместе с валютой его операций.

    Валюта в операцию копируется при сохранении, а не спрашивается у счёта
    при подсчётах, — поэтому просто переписать поле на счёте мало: операции
    остались бы в прежней валюте, и остаток стал бы суммой рублей с
    долларами как голых чисел. Раньше по этой причине смена и запрещалась
    вовсе.

    Что происходит: у каждой операции счёта валюта становится новой, а сумма
    в валюте установки считается заново — по курсу на дату самой операции, а
    не на сегодня. Сама сумма не трогается: человек ввёл её с чека, и
    поменялось только то, чем она подписана.

    Пересчёт задним числом стал возможен ровно тогда, когда сумма в валюте
    установки научилась быть пустой. До этого на месте недостающего курса
    молча стояла единица, и пересчёт полусотни старых операций записал бы
    полсотни курсов один к одному (см. services/currency_service.py).

    Переписываются только операции в прежней валюте счёта. Если у какой-то
    валюта была задана своя, она своей и останется: смена валюты счёта — не
    повод трогать то, что человек указал руками.

    Чего эта правка НЕ делает: она не переводит деньги из одной валюты в
    другую. Это исправление ошибки при заведении счёта — «вёл в долларах, а
    выбрал рубли». Если счёт действительно вёлся в прежней валюте, а теперь
    это другая карта, — это другой счёт, и заводить надо новый. Различить
    эти два случая приложение не может, поэтому форма предупреждает.
    """
    target = currency.upper()
    previous = account.currency.upper()
    if target == previous:
        return

    rows = (
        await session.execute(
            select(Transaction).where(
                Transaction.account_id == account.id,
                func.upper(Transaction.currency) == previous,
            )
        )
    ).scalars().all()
    for transaction in rows:
        transaction.currency = target
        rate, amount_base = await to_base(
            session, transaction.amount, target, transaction.date
        )
        transaction.exchange_rate = rate
        transaction.amount_base = amount_base

    await _recurrency_incoming_transfers(session, account, previous, target)
    account.currency = target


async def _recurrency_incoming_transfers(
    session: AsyncSession, account: Account, previous: str, target: str
) -> None:
    """Переводы НА этот счёт — вторая половина смены валюты.

    Перевод записан одной строкой, со стороны отправителя, и валюту
    получателя несёт отдельное поле. Со счётом меняется и оно, иначе на
    рублёвую карту, ставшую долларовой, продолжали бы приходить рубли.

    Второй случай хитрее. Пока обе карты были в одной валюте, пришедшая
    сумма не хранилась вовсе: она равнялась отправленной. После смены
    валюты равенство перестаёт быть правдой — и что именно пришло, не знает
    никто, включая приложение. Поэтому сумма записывается прежней, той же,
    что и была: смена валюты обещает не трогать числа, а только подпись под
    ними, и остаток счёта от неё не должен сдвинуться ни на копейку. Если
    на самом деле пришло другое, это правится в самой операции — там для
    того и появилось второе поле.
    """
    incoming = (
        await session.execute(
            select(Transaction).where(
                Transaction.transfer_account_id == account.id,
                Transaction.type == TransactionType.TRANSFER,
            )
        )
    ).scalars().all()

    for transaction in incoming:
        stated = (transaction.transfer_currency or "").upper()
        if stated == previous:
            transaction.transfer_currency = target
        elif not stated and transaction.currency.upper() != target:
            # Раньше валюты совпадали, теперь нет: пришедшую сумму надо
            # назвать явно, иначе её примут за отправленную.
            transaction.transfer_currency = target
            transaction.transfer_amount = transaction.amount
        else:
            continue
        _, transaction.transfer_amount_base = await to_base(
            session, transaction.transfer_amount, target, transaction.date
        )


async def update_account(session: AsyncSession, account_id: int, payload: AccountUpdate) -> AccountWithBalance:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    changes = payload.model_dump(exclude_unset=True)
    # Валюта снимается из общего списка полей: её меняет отдельный проход,
    # которому нужно прежнее значение — по нему он находит операции, чья
    # валюта досталась им от этого счёта.
    if changes.get("currency"):
        await _change_currency(session, account, changes.pop("currency"))
    # Смена вида счёта без явного указания природы переводит и природу —
    # иначе карта, ставшая кредитной, продолжила бы считаться активом.
    if "kind" in changes and "nature" not in changes:
        changes["nature"] = resolve_nature(changes["kind"], None)
    for field, value in changes.items():
        setattr(account, field, value)
    await session.commit()
    await session.refresh(account)
    balances = await get_balances_by_account(session)
    counts = await count_transactions_by_account(session)
    return _to_read(
        account,
        balances.get(account.id, Decimal("0")),
        transaction_count=counts.get(account.id, 0),
    )


async def delete_account(session: AsyncSession, account_id: int) -> None:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    await session.delete(account)
    await session.commit()
