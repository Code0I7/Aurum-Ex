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
from app.models.transaction import Transaction, TransactionCounterpartySplit
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
        # Валюты, в которых шли операции с этим человеком.
        #
        # Итоги считаются в валюте установки, по курсу дня каждой операции,
        # и это верно в смысле «сколько я в него вложил». Но если занимали
        # в чужой валюте, вопрос другой: заняв сто евро, ждут обратно сто
        # евро, а не то, сколько они стоили в тот вторник.
        #
        # Разделить долг по валютам — отдельная и немаленькая работа, и
        # начинать её ради случая, которого может не быть, незачем. Поэтому
        # пока честная пометка: тут сложены разные валюты, число приблизи-
        # тельное. Появится настоящий случай — сделаем как надо.
        self.currencies: set[str] = set()

    @property
    def mixed_currencies(self) -> bool:
        return len(self.currencies) > 1

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
    settlement_types = [TransactionType.EXTERNAL_IN, TransactionType.EXTERNAL_OUT]

    whole = (
        await session.execute(
            select(
                Transaction.counterparty_id,
                Transaction.type,
                Transaction.settlement_kind,
                Transaction.amount_base,
                Transaction.date,
                Transaction.currency,
            ).where(
                Transaction.counterparty_id.is_not(None),
                Transaction.type.in_(settlement_types),
                counted_only(),
            )
        )
    ).all()

    # Операция, разделённая между людьми, приходит сюда долями — по одной
    # строке на человека. Контрагент у неё пуст, поэтому в запрос выше она
    # не попадает вовсе: два ответа на вопрос «от кого» означали бы, что
    # операция посчитана дважды.
    #
    # Доля приводится к валюте установки тем же замороженным курсом, что и
    # вся операция: доли сходятся с её суммой, значит и приведённые доли
    # сойдутся с приведённой суммой. Курса нет — доля пуста, как и сама
    # операция, и в итоги не входит.
    shares = (
        await session.execute(
            select(
                TransactionCounterpartySplit.counterparty_id,
                Transaction.type,
                Transaction.settlement_kind,
                (TransactionCounterpartySplit.amount * Transaction.exchange_rate).label(
                    "amount_base"
                ),
                Transaction.date,
                Transaction.currency,
            )
            .join(Transaction, Transaction.id == TransactionCounterpartySplit.transaction_id)
            .where(
                TransactionCounterpartySplit.counterparty_id.is_not(None),
                Transaction.type.in_(settlement_types),
                counted_only(),
            )
        )
    ).all()

    rows = [*whole, *shares]

    counterparties = {
        row.id: row
        for row in (await session.execute(select(Counterparty))).scalars().all()
    }

    totals: dict[int, SettlementTotals] = {}
    for counterparty_id, tx_type, settlement, amount, tx_date, currency in rows:
        party = counterparties.get(counterparty_id)
        if party is None:
            continue
        # Без курса на дату складывать нечего: единица на её месте означала
        # бы, что сто долларов долга равны ста рублям.
        if amount is None:
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
        # Валюта операции — для пометки о смешанном итоге. Считается после
        # отсева транзита: он в расчёты не входит вовсе, и его валюта в
        # итоге не участвует.
        if currency:
            entry.currencies.add(currency.upper())
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



class TransitTotals:
    """Транзит по одному человеку: сколько его денег пришло и сколько ушло."""

    def __init__(self, counterparty: Counterparty) -> None:
        self.counterparty = counterparty
        self.received = Decimal("0")
        self.spent = Decimal("0")
        self.operations = 0

    @property
    def balance(self) -> Decimal:
        """Плюс — его деньги ещё лежат у вас, минус — вы вложили свои.

        Долгом это не является и в расчёты не входит: человек, недодавший на
        продукты, ничего не обязан возвращать, пока об этом не договорились.
        Но видеть разницу нужно — иначе непонятно, сошлось ли.
        """
        return self.received - self.spent


async def get_transit_by_person(
    session: AsyncSession, year: int | None = None, month: int | None = None
) -> list[TransitTotals]:
    """Транзит, разложенный по тому, ЧЬИ это были деньги.

    Ключ сложения — владелец денег, а не тот, с кем прошла операция:

        приход  — деньги дал counterparty, но принадлежать они могут
                  третьему, и тогда он указан в transit_party;
        расход  — деньги ушли к counterparty, но это могут быть чужие
                  деньги, которые просто идут дальше.

    Пустое поле означает «его» у прихода и «мои» у расхода — самый частый
    случай, ради которого заполнять ничего не нужно.

    Отсюда и весь расчёт. Брат передал 4 500 на покупки для мамы, я отдал
    маме эти 4 500 и ещё 370 своих: у брата приход и расход по 4 500 гасят
    друг друга — его деньги дошли, между нами не осталось ничего; у мамы
    остаются мои 370 со знаком минус. Ни «брату 4 500», ни «маме 4 870» не
    появляется ни с какой стороны: первое давно дошло, второе на три
    четверти состоит из чужих денег.

    Операция, у которой не указано вообще ничего, пропускается: записать
    её не на кого.
    """
    def in_period(stmt):
        if year is not None:
            stmt = stmt.where(func.extract("year", Transaction.date) == year)
        if month is not None:
            stmt = stmt.where(func.extract("month", Transaction.date) == month)
        return stmt

    stmt = in_period(
        select(
            Transaction.type,
            Transaction.counterparty_id,
            Transaction.transit_party_id,
            Transaction.amount,
        ).where(Transaction.settlement_kind == SettlementKind.TRANSIT, counted_only())
    )

    # Транзит, разделённый между людьми: у операции контрагент пуст, и
    # человек назван в доле. Вторая сторона (чьи деньги) остаётся на самой
    # операции — она одна на весь перевод.
    shares_stmt = in_period(
        select(
            Transaction.type,
            TransactionCounterpartySplit.counterparty_id,
            Transaction.transit_party_id,
            TransactionCounterpartySplit.amount,
        )
        .join(Transaction, Transaction.id == TransactionCounterpartySplit.transaction_id)
        .where(Transaction.settlement_kind == SettlementKind.TRANSIT, counted_only())
    )

    rows = [*(await session.execute(stmt)).all(), *(await session.execute(shares_stmt)).all()]
    counterparties = {
        row.id: row for row in (await session.execute(select(Counterparty))).scalars().all()
    }

    totals: dict[int, TransitTotals] = {}
    for tx_type, counterparty_id, transit_party_id, amount in rows:
        # Чьи это деньги. Не указано — значит, ничьих третьих здесь нет: у
        # прихода они того, кто передал, у расхода мои собственные, и счёт
        # в обоих случаях ведётся с тем, с кем прошла операция.
        owner_id = transit_party_id if transit_party_id is not None else counterparty_id
        party = counterparties.get(owner_id) if owner_id is not None else None
        if party is None:
            continue

        entry = totals.setdefault(owner_id, TransitTotals(party))
        entry.operations += 1
        if tx_type == TransactionType.EXTERNAL_IN:
            entry.received += amount
        else:
            entry.spent += amount

    # Сначала те, у кого не сошлось сильнее всего в минус: недостача — это
    # то, ради чего в список и смотрят.
    return sorted(totals.values(), key=lambda item: (item.balance, item.counterparty.name))

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
