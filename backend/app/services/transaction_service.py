"""Порядок операций внутри дня и баланс счёта после каждой операции.

Обе задачи вырастают из одного случая, обычного для самодельных таблиц.
Пусть в один день по счёту прошли приход, трата и перевод, и записаны они
только датой, без времени. Итог за день сойдётся при любом порядке, но
промежуточный баланс — нет: разложив их неудачно, получаем провал ниже
нуля в день, когда его не было.

Отсюда `day_order`: дата отвечает за день, порядковый номер — за
последовательность внутри него. Он проставляется сам, по времени ввода, и
правится перетаскиванием строки. Между днями строка не переносится: дату
меняют редактированием даты, а не движением мыши.

Баланс после операции считается оконной функцией по всей истории счёта, а
не по видимой странице: показать «баланс 350» на отфильтрованном списке,
где предыдущие операции скрыты, — значит показать неправду.
"""
from decimal import Decimal

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.enums import TransactionType
from app.models.transaction import Transaction

# Порядок, в котором операции идут по времени. Один и тот же кортеж нужен и
# оконной функции, и сортировке списка — иначе баланс в строке перестанет
# соответствовать её месту на экране.
CHRONOLOGICAL = (Transaction.date, Transaction.day_order, Transaction.id)


async def next_day_order(session: AsyncSession, account_id: int, on_date) -> int:
    """Следующий номер в пределах дня и счёта.

    Считается по счёту, а не по всей базе: порядок нужен, чтобы построить
    баланс конкретного счёта, и операции соседних счетов на него не влияют.
    """
    stmt = select(func.coalesce(func.max(Transaction.day_order), -1)).where(
        Transaction.account_id == account_id, Transaction.date == on_date
    )
    return int((await session.execute(stmt)).scalar_one()) + 1


def _signed_amount() -> object:
    """Сумма со знаком с точки зрения счёта в колонке account_id.

    EXTERNAL_IN и EXTERNAL_OUT двигают баланс наравне с доходом и расходом —
    разница только в том, что они не считаются заработком. Перевод уходит со
    счёта-источника; приход на счёт-получатель добавляется отдельно (см.
    running_balances), потому что для него эта строка — чужая.
    """
    return func.sum(
        case(
            (
                Transaction.is_excluded.is_(True),
                Decimal("0"),
            ),
            (
                Transaction.type.in_([TransactionType.INCOME, TransactionType.EXTERNAL_IN]),
                Transaction.amount_base,
            ),
            (
                Transaction.type.in_(
                    [TransactionType.EXPENSE, TransactionType.EXTERNAL_OUT, TransactionType.TRANSFER]
                ),
                -Transaction.amount_base,
            ),
            else_=Decimal("0"),
        )
    ).over(partition_by=Transaction.account_id, order_by=CHRONOLOGICAL)


def running_balance_subquery() -> Select:
    """Накопительный итог по каждому счёту на момент каждой операции.

    Считается по всей истории счёта, а не по отфильтрованной выборке:
    иначе «баланс после операции» менялся бы от того, какой фильтр включён,
    и переставал бы быть балансом.
    """
    return select(
        Transaction.id.label("transaction_id"),
        Transaction.account_id.label("account_id"),
        _signed_amount().label("running_delta"),
    ).subquery()


async def running_balances(session: AsyncSession, transaction_ids: list[int]) -> dict[int, Decimal]:
    """Баланс счёта после каждой из указанных операций.

    К накопительной сумме прибавляются начальный остаток счёта и приходы по
    переводам, адресованным этому счёту. Переводы учитываются отдельным
    запросом, а не оконной функцией: у строки перевода счёт-получатель лежит
    в другой колонке, и одним разбиением по account_id обе стороны не
    охватить.
    """
    if not transaction_ids:
        return {}

    sub = running_balance_subquery()
    rows = (
        await session.execute(
            select(sub.c.transaction_id, sub.c.account_id, sub.c.running_delta).where(
                sub.c.transaction_id.in_(transaction_ids)
            )
        )
    ).all()
    if not rows:
        return {}

    account_ids = {account_id for _, account_id, _ in rows}
    openings = dict(
        (
            await session.execute(select(Account.id, Account.opening_balance).where(Account.id.in_(account_ids)))
        ).all()
    )

    # Приходы по переводам, адресованным этим счетам.
    #
    # Сравниваются по дате и идентификатору, а НЕ по day_order — и это не
    # упрощение, а единственный осмысленный вариант. Номер внутри дня
    # локален для счёта: у перевода он проставлен в нумерации
    # счёта-источника, а сравнивать его надо с операциями получателя, где
    # своя нумерация с нуля. Сравнение чисел из двух разных нумераций даёт
    # произвольный результат — именно на этом первая версия и уронила тест,
    # потеряв приход. Идентификатор же растёт по времени ввода и одинаков
    # для всех счетов, поэтому внутри дня порядок задаёт он.
    anchors = (
        await session.execute(
            select(Transaction.id, Transaction.account_id, Transaction.date).where(
                Transaction.id.in_(transaction_ids)
            )
        )
    ).all()

    incoming_rows = (
        await session.execute(
            select(
                Transaction.transfer_account_id,
                Transaction.date,
                Transaction.id,
                Transaction.amount_base,
            ).where(
                Transaction.type == TransactionType.TRANSFER,
                Transaction.is_excluded.is_(False),
                Transaction.transfer_account_id.in_(account_ids),
            )
        )
    ).all()

    balances: dict[int, Decimal] = {}
    for tx_id, account_id, delta in rows:
        anchor = next((a for a in anchors if a[0] == tx_id), None)
        incoming = Decimal("0")
        if anchor is not None:
            _, _, anchor_date = anchor
            for dest_id, tx_date, other_id, amount in incoming_rows:
                if dest_id != account_id:
                    continue
                # «Не позже» этой операции: по дате, а внутри дня — по
                # порядку ввода.
                if (tx_date, other_id) <= (anchor_date, tx_id):
                    incoming += amount
        balances[tx_id] = (openings.get(account_id) or Decimal("0")) + (delta or Decimal("0")) + incoming

    return balances


def counted_only():
    """Условие «эта запись участвует в подсчётах».

    Одно место на все отчёты — иначе каждый сервис решает сам, и половина
    забывает. Ровно так и вышло: признак «не учитывать» добавили, обновили
    три сервиса из десяти, а движение денег продолжало вычитать возвращённые
    покупки.
    """
    return Transaction.is_excluded.is_(False)


def earnings_and_spending_only():
    """Условие «это заработок или трата».

    Переводы между своими счетами деньгами не становятся, а EXTERNAL_IN и
    EXTERNAL_OUT меняют баланс, но заработком не являются: жена передала на
    продукты — это не доход, и в норму сбережений попадать не должно.
    Поэтому фильтр перечисляет разрешённое, а не исключает переводы: при
    добавлении нового вида операции «всё, кроме перевода» тихо включило бы
    его в доходы.
    """
    return Transaction.type.in_([TransactionType.INCOME, TransactionType.EXPENSE])
