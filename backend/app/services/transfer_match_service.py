"""Перевод между своими счетами, записанный дважды.

Перевод — одна запись: она сама показывается исходящей в истории одного
счёта и входящей в истории другого. Но заносят его по выпискам, а выписок
две, по одной на банк, и один и тот же перевод легко попадает в приложение
дважды: сначала из выписки отправителя, потом из выписки получателя.
Остатки после этого врут на всю сумму, а если половины записаны тратой и
доходом — врут ещё и расходы с доходами.

Пара — две записи одного движения денег:

  * «половины» — трата на одном счёте и доход на другом. Склейка делает из
    траты перевод на счёт дохода, доход удаляется;
  * «перевод и приход» — перевод уже записан, а приход на счёт-получатель
    занесён ещё и доходом. Удаляется доход;
  * «перевод и списание» — то же со стороны отправителя. Удаляется трата;
  * «перевод дважды» — один перевод записан два раза. Остаётся тот, что
    записан раньше.

Совпадением считаются одна сумма в одной валюте и дни не дальше одного
друг от друга. На свой второй счёт перевод приходит сам и сразу, а разница
в день бывает только около полуночи, когда банки ставят разные даты.

Направление обязано совпасть. «Отправил и в тот же день вернул» — это два
настоящих перевода в разные стороны, и склеивать их между собой нечего:
четыре строки двух выписок дают два перевода, а не один и не четыре.

Только предлагается и никогда не склеивается само. Совпадение суммы и дня
бывает честным, а удалённую запись назад не вернуть. Отказ запоминается
(см. models/transfer_match.py).

Не участвуют:

  * «не учитывать» — такая запись уже выведена из итогов, и задвоенная
    строка как раз один из поводов её так пометить;
  * разделённые по категориям или по людям и с позициями чека — это покупка
    или расчёт, а не перевод, и склейка молча потеряла бы разбивку;
  * расчёты с людьми — перевод человеку не бывает половиной перевода между
    своими счетами.

Половины в разных валютах не ищутся: сравнить их суммы не с чем, курс банка
не равен курсу ЦБ. Перевод между валютами находит свою половину по той
сумме, что в нём записана для этой стороны.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date as date_
from datetime import timedelta
from decimal import Decimal
from enum import Enum

from fastapi import HTTPException
from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import TransactionType
from app.models.goal import GoalContribution
from app.models.transaction import (
    Transaction,
    TransactionCounterpartySplit,
    TransactionItem,
    TransactionSplit,
)
from app.models.transfer_match import TransferMatchDismissal
from app.services.transaction_service import counted_only

# На сколько дней могут разойтись даты двух записей одного перевода.
MATCH_WINDOW_DAYS = 1

# Длина поля описания в операции: склеенное описание обязано в неё влезть,
# иначе склейка упала бы на записи.
_DESCRIPTION_LIMIT = 255


class MatchKind(str, Enum):
    HALVES = "halves"
    TRANSFER_AND_IN = "transfer_and_in"
    TRANSFER_AND_OUT = "transfer_and_out"
    TRANSFER_TWICE = "transfer_twice"


# Какую пару брать, когда одна запись подходит в несколько. Сначала те, где
# перевод уже записан: там сомнений меньше всего — перевод есть, и вторая
# запись того же движения лишняя. Половины последними: из двух обычных
# операций перевод только предполагается.
_KIND_PRIORITY = {
    MatchKind.TRANSFER_TWICE: 0,
    MatchKind.TRANSFER_AND_IN: 1,
    MatchKind.TRANSFER_AND_OUT: 1,
    MatchKind.HALVES: 2,
}

_CANDIDATE_TYPES = (TransactionType.TRANSFER, TransactionType.EXPENSE, TransactionType.INCOME)


@dataclass(frozen=True)
class Movement:
    """Запись глазами поиска пар: с какого счёта ушло и на какой пришло."""

    id: int
    type: TransactionType
    date: date_
    account_id: int
    transfer_account_id: int | None
    amount: Decimal
    currency: str
    transfer_amount: Decimal | None = None
    transfer_currency: str | None = None

    @property
    def outgoing(self) -> tuple[Decimal, str]:
        return self.amount, self.currency.upper()

    @property
    def incoming(self) -> tuple[Decimal, str]:
        """Сколько и в чём пришло на счёт-получатель перевода. Пустая
        вторая сумма значит «столько же, сколько ушло»."""
        if self.transfer_amount is None:
            return self.outgoing
        return self.transfer_amount, (self.transfer_currency or self.currency).upper()


@dataclass(frozen=True)
class Match:
    kind: MatchKind
    # Запись, которая останется, и запись, которая уйдёт при склейке.
    keep_id: int
    drop_id: int
    days_apart: int


def pair_kind(a: Movement, b: Movement) -> Match | None:
    """Описывают ли две записи одно и то же движение денег, и как именно.

    Порядок аргументов не важен: ответ для (a, b) и (b, a) один.
    """
    if a.id == b.id:
        return None
    days = abs((a.date - b.date).days)
    if days > MATCH_WINDOW_DAYS:
        return None

    if a.type is b.type:
        if a.type is not TransactionType.TRANSFER:
            return None
        same = (
            a.account_id == b.account_id
            and a.transfer_account_id == b.transfer_account_id
            and a.outgoing == b.outgoing
            and a.incoming == b.incoming
        )
        if not same:
            return None
        # Остаётся записанный раньше: к нему, скорее всего, уже привыкли.
        keep, drop = sorted((a, b), key=lambda item: item.id)
        return Match(MatchKind.TRANSFER_TWICE, keep.id, drop.id, days)

    if {a.type, b.type} == {TransactionType.EXPENSE, TransactionType.INCOME}:
        out = a if a.type is TransactionType.EXPENSE else b
        into = b if out is a else a
        if out.account_id != into.account_id and out.outgoing == into.outgoing:
            return Match(MatchKind.HALVES, out.id, into.id, days)
        return None

    transfer = a if a.type is TransactionType.TRANSFER else b
    other = b if transfer is a else a
    if transfer.transfer_account_id is None:
        return None
    if other.type is TransactionType.INCOME:
        if other.account_id == transfer.transfer_account_id and other.outgoing == transfer.incoming:
            return Match(MatchKind.TRANSFER_AND_IN, transfer.id, other.id, days)
        return None
    if other.account_id == transfer.account_id and other.outgoing == transfer.outgoing:
        return Match(MatchKind.TRANSFER_AND_OUT, transfer.id, other.id, days)
    return None


def _pair_key(first_id: int, second_id: int) -> tuple[int, int]:
    return (first_id, second_id) if first_id < second_id else (second_id, first_id)


def _candidate_conditions() -> list:
    """Какие записи вообще могут оказаться половиной перевода (см. «Не
    участвуют» в описании модуля)."""
    return [
        counted_only(),
        Transaction.type.in_(_CANDIDATE_TYPES),
        ~exists().where(TransactionSplit.transaction_id == Transaction.id),
        ~exists().where(TransactionItem.transaction_id == Transaction.id),
        ~exists().where(TransactionCounterpartySplit.transaction_id == Transaction.id),
    ]


_MOVEMENT_COLUMNS = (
    Transaction.id,
    Transaction.type,
    Transaction.date,
    Transaction.account_id,
    Transaction.transfer_account_id,
    Transaction.amount,
    Transaction.currency,
    Transaction.transfer_amount,
    Transaction.transfer_currency,
)


def _movement_keys(movement: Movement) -> set[tuple[Decimal, str]]:
    keys = {movement.outgoing}
    if movement.type is TransactionType.TRANSFER:
        keys.add(movement.incoming)
    return keys


async def find_matches(session: AsyncSession) -> list[Match]:
    """Все пары, похожие на один перевод, записанный дважды.

    Каждая запись попадает не больше чем в одну пару. Когда подходит
    несколько, берётся ближайшая по дате, затем по виду пары (см.
    _KIND_PRIORITY), затем записанная ближе по времени ввода. После
    склейки оставшиеся найдутся заново: три записи одного перевода
    сходятся в одну за две склейки.

    Отклонённые пары не возвращаются.
    """
    rows = (await session.execute(select(*_MOVEMENT_COLUMNS).where(*_candidate_conditions()))).all()
    movements = [Movement(*row) for row in rows]

    # Сравниваются только записи с одной суммой: сравнивать всё со всем
    # значило бы квадрат от числа операций.
    by_amount: dict[tuple[Decimal, str], list[Movement]] = defaultdict(list)
    for movement in movements:
        for key in _movement_keys(movement):
            by_amount[key].append(movement)

    dismissed = {
        (first, second)
        for first, second in (
            await session.execute(
                select(TransferMatchDismissal.first_id, TransferMatchDismissal.second_id)
            )
        ).all()
    }

    found: dict[tuple[int, int], Match] = {}
    for group in by_amount.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda item: item.date)
        for index, first in enumerate(group):
            for second in group[index + 1 :]:
                if (second.date - first.date).days > MATCH_WINDOW_DAYS:
                    break
                key = _pair_key(first.id, second.id)
                if key in found or key in dismissed:
                    continue
                match = pair_kind(first, second)
                if match is not None:
                    found[key] = match

    ordered = sorted(
        found.values(),
        key=lambda match: (match.days_apart, _KIND_PRIORITY[match.kind], abs(match.keep_id - match.drop_id)),
    )
    used: set[int] = set()
    chosen: list[Match] = []
    for match in ordered:
        if match.keep_id in used or match.drop_id in used:
            continue
        used.update((match.keep_id, match.drop_id))
        chosen.append(match)
    return chosen


async def find_counterparts(
    session: AsyncSession, draft: Movement, limit: int = 5
) -> list[tuple[MatchKind, int]]:
    """Уже записанные операции, с которыми вводимая сложилась бы в пару.

    Спрашивается формой перед записью: пока человек идёт по выписке
    второго банка, ему лучше узнать, что этот перевод уже есть, до того,
    как он станет второй записью. Отклонённые пары здесь не учитываются —
    у вводимой операции ещё нет номера, чтобы что-то о ней решить.
    """
    amounts = {amount for amount, _ in _movement_keys(draft)}
    rows = (
        await session.execute(
            select(*_MOVEMENT_COLUMNS).where(
                *_candidate_conditions(),
                Transaction.date >= draft.date - timedelta(days=MATCH_WINDOW_DAYS),
                Transaction.date <= draft.date + timedelta(days=MATCH_WINDOW_DAYS),
                Transaction.amount.in_(amounts) | Transaction.transfer_amount.in_(amounts),
            )
        )
    ).all()

    found: list[tuple[int, MatchKind, int]] = []
    for row in rows:
        existing = Movement(*row)
        match = pair_kind(draft, existing)
        if match is not None:
            found.append((match.days_apart, match.kind, existing.id))
    found.sort(key=lambda item: (item[0], _KIND_PRIORITY[item[1]], -item[2]))
    return [(kind, transaction_id) for _, kind, transaction_id in found[:limit]]


def _movement_of(transaction: Transaction) -> Movement:
    return Movement(
        id=transaction.id,
        type=transaction.type,
        date=transaction.date,
        account_id=transaction.account_id,
        transfer_account_id=transaction.transfer_account_id,
        amount=transaction.amount,
        currency=transaction.currency,
        transfer_amount=transaction.transfer_amount,
        transfer_currency=transaction.transfer_currency,
    )


def _merged_description(kept: str | None, dropped: str | None) -> str | None:
    """Описание склеенной записи: у каждой половины своё, и терять ни одно
    нельзя — в выписке отправителя одно название, у получателя другое."""
    first = (kept or "").strip()
    second = (dropped or "").strip()
    if not first:
        return second or None
    if not second or second.lower() == first.lower():
        return first
    return f"{first} · {second}"[:_DESCRIPTION_LIMIT]


async def _load_pair(session: AsyncSession, first_id: int, second_id: int) -> list[Transaction]:
    if first_id == second_id:
        raise HTTPException(status_code=400, detail="A pair needs two different transactions")
    rows = (
        await session.execute(
            select(Transaction)
            .options(
                selectinload(Transaction.tags),
                selectinload(Transaction.splits),
                selectinload(Transaction.items),
                selectinload(Transaction.counterparty_splits),
            )
            .where(Transaction.id.in_([first_id, second_id]))
        )
    ).scalars().all()
    if len(rows) != 2:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return list(rows)


async def merge_match(session: AsyncSession, first_id: int, second_id: int) -> int:
    """Склеивает пару в одну запись и возвращает номер оставшейся.

    Пара проверяется заново, а не принимается на веру: между показом списка
    и нажатием запись могли поправить, и склеивать то, что парой уже не
    является, нельзя.
    """
    pair = await _load_pair(session, first_id, second_id)
    for transaction in pair:
        if (
            transaction.is_excluded
            or transaction.type not in _CANDIDATE_TYPES
            or transaction.splits
            or transaction.items
            or transaction.counterparty_splits
        ):
            raise HTTPException(status_code=409, detail="These transactions no longer form a match")
    match = pair_kind(_movement_of(pair[0]), _movement_of(pair[1]))
    if match is None:
        raise HTTPException(status_code=409, detail="These transactions no longer form a match")

    by_id = {transaction.id: transaction for transaction in pair}
    keep, drop = by_id[match.keep_id], by_id[match.drop_id]

    if match.kind is MatchKind.HALVES:
        # Трата становится переводом на счёт дохода. Дата — списания: деньги
        # ушли в этот день, и остаток отправителя обязан это показать.
        keep.type = TransactionType.TRANSFER
        keep.transfer_account_id = drop.account_id
        # У перевода категории нет: он не трата и не доход.
        keep.category_id = None
        # Валюта у половин одна (иначе пары бы не было), и второй суммы у
        # перевода не существует — см. models/transaction.py.
        keep.transfer_amount = None
        keep.transfer_currency = None
        keep.transfer_amount_base = None

    keep.description = _merged_description(keep.description, drop.description)
    for tag in drop.tags:
        if tag not in keep.tags:
            keep.tags.append(tag)

    # Взнос в цель, сделанный удаляемой записью, переходит к оставшейся:
    # иначе склейка молча отвязала бы его от операции.
    await session.execute(
        update(GoalContribution)
        .where(GoalContribution.transaction_id == drop.id)
        .values(transaction_id=keep.id)
    )
    await session.delete(drop)
    await session.commit()
    return keep.id


async def dismiss_match(session: AsyncSession, first_id: int, second_id: int) -> None:
    """Запоминает, что пара — две разные операции."""
    await _load_pair(session, first_id, second_id)
    first, second = _pair_key(first_id, second_id)
    if await session.get(TransferMatchDismissal, (first, second)) is None:
        session.add(TransferMatchDismissal(first_id=first, second_id=second))
        await session.commit()
