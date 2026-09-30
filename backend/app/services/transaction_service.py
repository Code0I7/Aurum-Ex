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
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.account import Account
from app.models.enums import TransactionType
from app.models.transaction import Transaction

# Порядок, в котором операции идут по времени. Один и тот же кортеж нужен и
# оконной функции, и сортировке списка — иначе баланс в строке перестанет
# соответствовать её месту на экране.
CHRONOLOGICAL = (Transaction.date, Transaction.day_order, Transaction.id)


async def next_day_order(session: AsyncSession, on_date) -> int:
    """Следующий номер в пределах дня — по всем счетам сразу.

    Раньше нумерация шла внутри счёта: считалось, что порядок нужен только
    для баланса, а операции соседних счетов на него не влияют. Для баланса
    это по-прежнему так — он считается оконной функцией с разбиением по
    счёту, и сквозная нумерация дня ему безразлична.

    Но порядок виден и в самом списке, где счета идут вперемешку. При
    нумерации по счёту у покупки наличными и покупки картой в один день
    оказывался один и тот же номер, и поднять наличную выше карточной было
    нельзя: список сортируется по номеру, а он у них совпадал. Сквозная
    нумерация дня делает порядок дня тем, что человек видит и может
    переставить.
    """
    stmt = select(func.coalesce(func.max(Transaction.day_order), -1)).where(
        Transaction.date == on_date
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
            # Сумма в валюте счёта, а не в валюте установки. Остаток — это
            # состояние: сто долларов на карте остаются ста долларами, и
            # подпись у числа стоит долларовая. Пересчёт — вопрос другой, и
            # ответ на него даёт карточка счёта.
            (
                Transaction.type.in_([TransactionType.INCOME, TransactionType.EXTERNAL_IN]),
                Transaction.amount,
            ),
            (
                Transaction.type.in_(
                    [TransactionType.EXPENSE, TransactionType.EXTERNAL_OUT, TransactionType.TRANSFER]
                ),
                -Transaction.amount,
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


async def find_similar_transactions(
    session: AsyncSession,
    *,
    on_date: date_,
    transaction_type: TransactionType,
    amount: Decimal,
    description: str,
    limit: int = 5,
) -> list[Transaction]:
    """Уже записанные операции того же дня, неотличимые от вводимой.

    Нужно из-за того, как люди на самом деле ведут учёт: не подряд, а
    вперемешку — сегодняшнее сразу, вчерашнее и позавчерашнее потом. При
    таком вводе легко записать одну покупку дважды и не заметить, потому
    что в списке она окажется не рядом с собой, а среди чужих дней.

    Совпадением считается день, вид, сумма и описание — то, что человек
    видит в строке. Счёт в сравнение НЕ входит: перепутанный счёт при
    повторном вводе такая же ошибка, как и всё остальное, и прятать из-за
    него предупреждение значило бы пропускать именно тот случай, ради
    которого оно заводится. Сам счёт показывается в предупреждении, чтобы
    человек увидел разницу и решил сам.

    Настоящие повторы дня — две поездки на автобусе — тоже попадут сюда, и
    это нормально: предупреждение спрашивает, а не запрещает, и такой
    повтор человек помнит.

    Без описания не ищем ничего. Описание необязательно с beta.4, так что
    пустым оно приходит сплошь и рядом, а по одним лишь дню и сумме под
    совпадение попадает слишком много чужого — две поездки на автобусе,
    два кофе, — и предупреждение превращается в шум, который перестают
    читать.
    """
    normalized = description.strip().lower()
    if not normalized:
        return []

    conditions = [
        Transaction.date == on_date,
        Transaction.type == transaction_type,
        Transaction.amount == amount,
        func.lower(func.trim(Transaction.description)) == normalized,
    ]

    rows = (
        await session.execute(
            select(Transaction)
            .options(selectinload(Transaction.account), selectinload(Transaction.category))
            .where(*conditions)
            .order_by(Transaction.day_order, Transaction.id)
            .limit(limit)
        )
    ).scalars()
    return list(rows)


async def running_balances(
    session: AsyncSession, transaction_ids: list[int], for_account_id: int | None = None
) -> dict[int, Decimal]:
    """Баланс счёта после каждой из указанных операций.

    К накопительной сумме прибавляются начальный остаток счёта и приходы по
    переводам, адресованным этому счёту. Переводы учитываются отдельным
    запросом, а не оконной функцией: у строки перевода счёт-получатель лежит
    в другой колонке, и одним разбиением по account_id обе стороны не
    охватить.

    `for_account_id` — когда список отфильтрован по одному счёту, баланс
    считается для НЕГО, а не для того, что записан в строке. Иначе у строки
    перевода в выписке получателя показывался бы остаток отправителя: на
    паре счетов вроде «карта и рассрочка того же магазина» это выглядит как
    деньги, взявшиеся ниоткуда, и запутывает ровно там, где выписка и нужна.
    Для этого случая счёт идёт отдельным путём — см. _statement_balances.
    """
    if not transaction_ids:
        return {}

    if for_account_id is not None:
        return await _statement_balances(session, transaction_ids, for_account_id)

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
    # Порядок ровно тот же, каким список идёт на экране: (дата, номер в дне,
    # id). Раньше здесь сравнивались только дата и id — считалось, что номер
    # в дне локален для счёта и сравнивать его с чужой нумерацией нельзя. С
    # тех пор номер стал сквозным по дню (см. next_day_order), а сравнение
    # осталось прежним, и приход попадал в накопительную сумму не там, где
    # строка стоит в списке: в дне, где перевод введён раньше соседней
    # операции, но показан ниже неё, «баланс после» прыгал вверх и обратно.
    # Чем больше переводов в дне, тем дальше уезжала колонка.
    #
    # Ключ сортировки должен совпадать с тем, по которому список
    # выводится, иначе колонка перестаёт быть балансом: она обязана
    # читаться сверху вниз как последовательность остатков.
    anchors = (
        await session.execute(
            select(
                Transaction.id,
                Transaction.account_id,
                Transaction.date,
                Transaction.day_order,
            ).where(Transaction.id.in_(transaction_ids))
        )
    ).all()

    incoming_rows = (
        await session.execute(
            select(
                Transaction.transfer_account_id,
                Transaction.date,
                Transaction.day_order,
                Transaction.id,
                # Тоже в валюте счёта — см. running_balance выше. Для
                # перевода между валютами это пришедшая сумма: на счёт
                # получателя легло именно столько.
                func.coalesce(Transaction.transfer_amount, Transaction.amount),
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
            _, _, anchor_date, anchor_order = anchor
            for dest_id, tx_date, tx_order, other_id, amount in incoming_rows:
                if dest_id != account_id:
                    continue
                # «Не позже» этой операции в том порядке, в каком список
                # показан: дата, номер в дне, идентификатор.
                if (tx_date, tx_order, other_id) <= (anchor_date, anchor_order, tx_id):
                    incoming += amount
        balances[tx_id] = (openings.get(account_id) or Decimal("0")) + (delta or Decimal("0")) + incoming

    return balances


async def _statement_balances(
    session: AsyncSession, transaction_ids: list[int], account_id: int
) -> dict[int, Decimal]:
    """Баланс счёта после каждой строки его выписки.

    Выписка показывает обе стороны перевода, и строка, пришедшая переводом,
    принадлежит другому счёту. Оконная функция по account_id для неё
    бесполезна: там накопительная сумма отправителя. Поэтому здесь берутся
    все движения счёта разом — свои операции со знаком и приходы по
    переводам, — выстраиваются в порядке показа и складываются нарастающим
    итогом. Нужная строка находится по своему месту в этом ряду.

    Так «баланс после» у строки означает ровно то, что написано: сколько
    было на счёте сразу после неё. Прежняя схема обнуляла для чужих строк
    накопительную сумму целиком, и вместе с чужим числом пропадала вся
    собственная история счёта: оставались начальный остаток и приходы.
    """
    own = (
        await session.execute(
            select(
                Transaction.id,
                Transaction.date,
                Transaction.day_order,
                Transaction.type,
                Transaction.amount,
                Transaction.is_excluded,
            ).where(Transaction.account_id == account_id)
        )
    ).all()

    incoming = (
        await session.execute(
            select(
                Transaction.id,
                Transaction.date,
                Transaction.day_order,
                func.coalesce(Transaction.transfer_amount, Transaction.amount),
            ).where(
                Transaction.type == TransactionType.TRANSFER,
                Transaction.is_excluded.is_(False),
                Transaction.transfer_account_id == account_id,
            )
        )
    ).all()

    movements: list[tuple[tuple, int, Decimal]] = []
    for tx_id, tx_date, day_order, tx_type, amount, is_excluded in own:
        if is_excluded:
            # Помеченное «не учитывать» остаётся в списке, но на деньги не
            # влияет: баланс после такой строки равен балансу до неё.
            delta = Decimal("0")
        elif tx_type in (TransactionType.INCOME, TransactionType.EXTERNAL_IN):
            delta = amount
        elif tx_type in (
            TransactionType.EXPENSE,
            TransactionType.EXTERNAL_OUT,
            TransactionType.TRANSFER,
        ):
            delta = -amount
        else:
            delta = Decimal("0")
        movements.append(((tx_date, day_order, tx_id), tx_id, delta))

    for tx_id, tx_date, day_order, amount in incoming:
        # Перевод между своими счетами попадает сюда и как своя операция
        # (ушло), и как приход (пришло) — для перевода на самого себя это
        # верно: две записи одной строки гасят друг друга.
        movements.append(((tx_date, day_order, tx_id), tx_id, amount))

    movements.sort(key=lambda item: item[0])

    opening = (
        await session.execute(select(Account.opening_balance).where(Account.id == account_id))
    ).scalar_one_or_none() or Decimal("0")

    wanted = set(transaction_ids)
    balances: dict[int, Decimal] = {}
    total = opening
    for _key, tx_id, delta in movements:
        total += delta
        # У перевода на самого себя две записи подряд; баланс строки — тот,
        # что получился после обеих, поэтому значение перезаписывается.
        if tx_id in wanted:
            balances[tx_id] = total

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


def converted_only():
    """Условие «сумму операции есть в чём сложить с остальными».

    Итог складывает операции разных счетов, а значит и разных валют, и
    складывать можно только суммы в валюте установки — Transaction.amount_base.
    Раньше итоги брали сумму операции как есть: пока все счета рублёвые, это
    незаметно, но одна трата на 100 € входила в расходы как 100 ₽.

    Операция без курса на свою дату пропускается, как и в капитале: число,
    выдуманное из единицы вместо курса, хуже пропуска (см. to_base).
    Остаток счёта сюда не относится — он состояние, и считается в валюте
    самого счёта.
    """
    return Transaction.amount_base.is_not(None)


def split_base_amount(split_amount):
    """Доля разделённой операции в валюте установки.

    Своей приведённой суммы у доли нет, и приводится она тем же курсом,
    что заморожен в операции: доли сходятся с суммой операции, значит и
    приведённые доли сходятся с приведённой суммой — с точностью до
    копейки на округлении.
    """
    return func.round(split_amount * Transaction.exchange_rate, 2)
