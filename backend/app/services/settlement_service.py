"""Расчёты с людьми: кто сколько передал, кто кому должен.

Две разные величины, и путать их нельзя.

**Оборот** — сколько денег вообще прошло через человека. Жена за четыре года
передала полмиллиона на продукты: цифра полезная, но долгом не является и
возврата не подразумевает.

**Долг** — только то, что помечено как заём. Он возникает, когда деньги дали
или взяли с расчётом вернуть, и гасится возвратом. Подарок долга не создаёт,
сколько бы раз он ни повторился.

В самодельных таблицах эти две вещи неразличимы: там всё сваливается в
категории вроде «Долги — Возврат» и «Долги — Погашение», а сколько сейчас
висит на конкретном человеке, приходится держать в голове или считать
формулой в стороне. Здесь остаток считается сам.

Знак остатка читается так:

  * **положительный** — этот человек должен вам;
  * **отрицательный** — вы должны ему.
"""
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.counterparty import Counterparty
from app.models.enums import SettlementKind, TransactionType
from app.models.transaction import Transaction
from app.services.transaction_service import counted_only


class SettlementTotals:
    """Итоги по одному человеку."""

    def __init__(self, counterparty: Counterparty) -> None:
        self.counterparty = counterparty
        # Оборот: сколько всего пришло от него и ушло к нему.
        self.received = Decimal("0")
        self.given = Decimal("0")
        # Долговая часть оборота.
        self.owed_to_me = Decimal("0")
        self.owed_by_me = Decimal("0")
        self.last_date = None
        self.operations = 0

    @property
    def balance(self) -> Decimal:
        """Остаток долга: плюс — должны вам, минус — должны вы."""
        return self.owed_to_me - self.owed_by_me


async def get_settlements(session: AsyncSession) -> list[SettlementTotals]:
    """Считает обороты и остатки долгов по каждому контрагенту.

    Возвращаются все контрагенты, у которых была хоть одна операция —
    включая тех, с кем рассчитались полностью. Человек с нулевым остатком
    это не пустая строка, а закрытый долг, и убирать его из списка значит
    прятать факт, что он был.
    """
    rows = (
        await session.execute(
            select(
                Transaction.counterparty_id,
                Transaction.type,
                Transaction.settlement_kind,
                Transaction.amount_base,
                Transaction.date,
            ).where(
                Transaction.counterparty_id.is_not(None),
                Transaction.type.in_([TransactionType.EXTERNAL_IN, TransactionType.EXTERNAL_OUT]),
                counted_only(),
            )
        )
    ).all()

    counterparties = {
        row.id: row
        for row in (await session.execute(select(Counterparty))).scalars().all()
    }

    totals: dict[int, SettlementTotals] = {}
    for counterparty_id, tx_type, settlement, amount, tx_date in rows:
        party = counterparties.get(counterparty_id)
        if party is None:
            continue

        # Транзит в расчёты с человеком не входит вовсе — ни в долг, ни в
        # оборот.
        #
        # В долг он не входил и раньше: деньги, прошедшие насквозь, никому
        # ничего не должны. Но он попадал в оборот, и от этого читалось
        # неправильное: получил от Ивана тысячу и передал её Ольге —
        # Иван числится дающим, Ольга берущей, будто один щедрый, а
        # вторая просила. На самом деле между ними и мной не происходило
        # ничего: деньги полежали на счёте и ушли дальше.
        #
        # Сколько всего прошло и сколько чужого лежит сейчас, показывается
        # отдельно — см. get_transit_summary.
        if settlement == SettlementKind.TRANSIT:
            continue
        entry = totals.setdefault(counterparty_id, SettlementTotals(party))
        entry.operations += 1
        if entry.last_date is None or tx_date > entry.last_date:
            entry.last_date = tx_date

        incoming = tx_type == TransactionType.EXTERNAL_IN
        if incoming:
            entry.received += amount
        else:
            entry.given += amount

        # Долг двигают только заём и его погашение. Подарок и транзит
        # остаются в обороте и в остаток не попадают — иначе каждая
        # переданная на продукты тысяча превращалась бы в требование
        # вернуть, а чужие деньги, полежавшие на счёте, — в чей-то долг.
        #
        # В обороте они при этом остаются намеренно: от этого человека
        # деньги действительно приходили, а тому действительно уходили, и
        # «сколько всего прошло между нами» — честное число.
        if settlement == SettlementKind.LOAN_OUT:
            # Дал в долг: деньги ушли, человек должен.
            entry.owed_to_me += amount
        elif settlement == SettlementKind.LOAN_IN:
            # Занял: деньги пришли, должен я.
            entry.owed_by_me += amount
        elif settlement == SettlementKind.REPAYMENT:
            # Погашение уменьшает ту сторону, откуда пришли деньги: вернули
            # мне — уменьшается его долг, вернул я — мой.
            if incoming:
                entry.owed_to_me -= amount
            else:
                entry.owed_by_me -= amount

    return sorted(
        totals.values(),
        # Сначала те, кто должен больше всего, затем нулевые, затем те, кому
        # должны вы — так список читается как ответ на вопрос «где мои
        # деньги».
        key=lambda item: (-item.balance, item.counterparty.name),
    )


async def get_settlement_summary(session: AsyncSession) -> dict[str, Decimal]:
    """Две итоговые суммы для карточки капитала.

    Показываются рядом с капиталом, но НЕ входят в него: деньги, которые
    вам должны, лежат не у вас, а обещание вернуть — не актив, пока его не
    вернули.
    """
    settlements = await get_settlements(session)
    return {
        "owed_to_me": sum((item.balance for item in settlements if item.balance > 0), Decimal("0")),
        "owed_by_me": -sum((item.balance for item in settlements if item.balance < 0), Decimal("0")),
    }


async def get_transit_summary(session: AsyncSession) -> dict[str, Decimal]:
    """Деньги, прошедшие через счёт насквозь.

    В расчёты с людьми они не входят (см. get_settlements), но и молчать о
    них нельзя: чужая тысяча, полежавшая на карте неделю, — это реальные
    деньги, которые нельзя тратить, и человек должен видеть, сколько их.

    Считается двумя числами:

      * **прошло через меня** — сколько уже ушло дальше. Отвечает на «какой
        оборот прошёл мимо меня за всё время»;
      * **ещё не передано** — разница между полученным и отданным, то есть
        чужое, лежащее на счёте прямо сейчас.

    Второе может уйти в минус — значит, передал вперёд из своих, ещё не
    получив. Это не ошибка и не выпрямляется в ноль: минус здесь и означает
    «мне должны вернуть», просто человек не пометил это займом.
    """
    rows = (
        await session.execute(
            select(Transaction.type, func.coalesce(func.sum(Transaction.amount_base), 0))
            .where(
                Transaction.settlement_kind == SettlementKind.TRANSIT,
                Transaction.type.in_([TransactionType.EXTERNAL_IN, TransactionType.EXTERNAL_OUT]),
                counted_only(),
            )
            .group_by(Transaction.type)
        )
    ).all()
    by_type = {tx_type: Decimal(amount) for tx_type, amount in rows}
    received = by_type.get(TransactionType.EXTERNAL_IN, Decimal("0"))
    passed_on = by_type.get(TransactionType.EXTERNAL_OUT, Decimal("0"))
    return {"passed_through": passed_on, "held": received - passed_on}


async def get_reserved_by_account(session: AsyncSession) -> dict[int, Decimal]:
    """Сколько на каждом счёте отложено под цели.

    Резерв не уменьшает баланс: деньги лежат там же, где лежали, просто
    часть их обещана другой задаче. Счёт показывает три числа — всего,
    отложено, доступно, — и второе берётся отсюда.
    """
    from app.models.enums import GoalStatus
    from app.models.goal import Goal, GoalContribution

    # Счёт берётся у взноса, а не у цели: копить можно с нескольких
    # счетов, и «три тысячи наличными, две безналом» — это две разные
    # пометки на двух разных остатках, а не одна на пять тысяч.
    rows = (
        await session.execute(
            select(GoalContribution.account_id, GoalContribution.amount)
            .join(Goal, Goal.id == GoalContribution.goal_id)
            .where(GoalContribution.account_id.is_not(None), Goal.status == GoalStatus.ACTIVE)
        )
    ).all()

    reserved: dict[int, Decimal] = defaultdict(Decimal)
    for account_id, amount in rows:
        reserved[account_id] += amount
    # Отрицательный резерв бессмыслен: он получается, когда из цели сняли
    # больше, чем отложили, а такое бывает при импорте старых данных.
    return {account_id: max(value, Decimal("0")) for account_id, value in reserved.items()}
