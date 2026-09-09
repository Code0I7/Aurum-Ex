"""Расчёты с людьми: обороты, долги, резервы целей.

Главное, что здесь проверяется, — различие между оборотом и долгом. В
самодельных таблицах его нет: всё сваливается в категории вроде «Долги —
Возврат», и сколько сейчас висит на конкретном человеке, приходится
держать в голове.
"""
from decimal import Decimal

from httpx import AsyncClient


def money(value: str) -> Decimal:
    """Суммы сверяются как числа, а не как строки: тест про смысл долга, а
    не про то, сколько нулей API дописал после запятой."""
    return Decimal(value)


async def _counterparty(client: AsyncClient, name: str) -> int:
    return (await client.post("/counterparties", json={"name": name})).json()["id"]


async def _move(
    client: AsyncClient,
    account_id: int,
    counterparty_id: int,
    *,
    incoming: bool,
    amount: str,
    settlement: str,
    date: str = "2026-09-01",
) -> None:
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "external_in" if incoming else "external_out",
            "amount": amount,
            "description": "Расчёт",
            "date": date,
            "counterparty_id": counterparty_id,
            "settlement_kind": settlement,
            "category_id": None,
        },
    )
    assert resp.status_code == 201, resp.text


async def test_a_gift_moves_the_balance_but_creates_no_debt(client: AsyncClient, account_id):
    """Жена передала на продукты — это не заём. Деньги на счёте прибавились,
    но требования вернуть не возникло."""
    party = await _counterparty(client, "Жена")
    await _move(client, account_id, party, incoming=True, amount="3000.00", settlement="gift")

    rows = (await client.get("/settlements")).json()
    assert len(rows) == 1
    assert money(rows[0]["received"]) == Decimal("3000")
    assert money(rows[0]["balance"]) == Decimal("0")

    # И в заработок это тоже не попало — иначе норма сбережений завралась бы.
    dashboard = (await client.get("/dashboard/summary?year=2026&month=9")).json()
    assert money(dashboard["real_income"]) == Decimal("0")


async def test_a_loan_creates_a_debt_and_repayment_closes_it(client: AsyncClient, account_id):
    party = await _counterparty(client, "Друг")
    await _move(client, account_id, party, incoming=False, amount="5000.00", settlement="loan_out")

    rows = (await client.get("/settlements")).json()
    assert money(rows[0]["owed_to_me"]) == Decimal("5000")
    assert money(rows[0]["balance"]) == Decimal("5000")

    # Вернул половину.
    await _move(
        client, account_id, party, incoming=True, amount="2000.00", settlement="repayment", date="2026-09-10"
    )
    rows = (await client.get("/settlements")).json()
    assert money(rows[0]["balance"]) == Decimal("3000")

    # Вернул остаток — долг закрыт, но человек из списка не исчезает:
    # закрытый долг это факт, а не пустая строка.
    await _move(
        client, account_id, party, incoming=True, amount="3000.00", settlement="repayment", date="2026-09-20"
    )
    rows = (await client.get("/settlements")).json()
    assert money(rows[0]["balance"]) == Decimal("0")
    assert rows[0]["operations"] == 3


async def test_borrowing_shows_up_as_my_debt(client: AsyncClient, account_id):
    party = await _counterparty(client, "Брат")
    await _move(client, account_id, party, incoming=True, amount="10000.00", settlement="loan_in")

    rows = (await client.get("/settlements")).json()
    assert money(rows[0]["owed_by_me"]) == Decimal("10000")
    assert money(rows[0]["balance"]) == Decimal("-10000")

    summary = (await client.get("/settlements/summary")).json()
    assert money(summary["owed_by_me"]) == Decimal("10000")
    assert money(summary["owed_to_me"]) == Decimal("0")


async def test_the_same_person_can_gift_and_lend(client: AsyncClient, account_id):
    """Признак возвратности стоит на операции, а не на человеке: один и тот
    же человек и дарит, и одалживает."""
    party = await _counterparty(client, "Мама")
    await _move(client, account_id, party, incoming=True, amount="4000.00", settlement="gift")
    await _move(client, account_id, party, incoming=True, amount="6000.00", settlement="loan_in")

    rows = (await client.get("/settlements")).json()
    # Оборот включает обе операции, долг — только вторую.
    assert money(rows[0]["received"]) == Decimal("10000")
    assert money(rows[0]["balance"]) == Decimal("-6000")


async def test_excluded_settlements_are_ignored(client: AsyncClient, account_id):
    """Отменённый перевод остаётся в истории, но долга не создаёт."""
    party = await _counterparty(client, "Коллега")
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "external_out",
            "amount": "1500.00",
            "description": "Ошибочный перевод",
            "date": "2026-09-01",
            "counterparty_id": party,
            "settlement_kind": "loan_out",
            "is_excluded": True,
            "category_id": None,
        },
    )
    assert resp.status_code == 201

    assert (await client.get("/settlements")).json() == []


async def test_goal_reserve_splits_the_account_balance(client: AsyncClient, account_id, categories):
    """Счёт читается тремя числами: всего, отложено, доступно. Резерв не
    уменьшает баланс — деньги лежат там же, просто часть обещана цели."""
    await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "income",
            "amount": "50000.00",
            "description": "Зарплата",
            "date": "2026-09-01",
            "category_id": categories["Salary"]["id"],
        },
    )
    goal = (
        await client.post(
            "/goals",
            json={"name": "Новый телефон", "target_amount": "30000.00", "account_id": account_id},
        )
    ).json()
    await client.post(f"/goals/{goal['id']}/contributions", json={"amount": "8000.00", "date": "2026-09-02"})

    account = next(row for row in (await client.get("/accounts")).json() if row["id"] == account_id)
    assert money(account["balance"]) == Decimal("50000")
    assert money(account["reserved"]) == Decimal("8000")
    assert money(account["available"]) == Decimal("42000")


async def test_reserve_never_pushes_available_below_zero(client: AsyncClient, account_id):
    """Отложено больше, чем есть на счёте: свободных денег нет, но и долга
    это не создаёт."""
    goal = (
        await client.post(
            "/goals",
            json={"name": "Мечта", "target_amount": "100000.00", "account_id": account_id},
        )
    ).json()
    await client.post(f"/goals/{goal['id']}/contributions", json={"amount": "9000.00", "date": "2026-09-02"})

    account = next(row for row in (await client.get("/accounts")).json() if row["id"] == account_id)
    assert money(account["available"]) == Decimal("0")


async def test_transit_moves_the_turnover_but_never_the_debt(client: AsyncClient, account_id):
    """Деньги прошли через счёт: получил от одного, передал другому.

    Это не подарок и не заём. Долга не возникает ни в одну сторону — иначе
    касса на общий подарок превращалась бы в чьё-то обязательство, — но в
    обороте с человеком движение остаётся: от него деньги действительно
    приходили.
    """
    ivan = await _counterparty(client, "Иван")
    olga = await _counterparty(client, "Ольга")
    await _move(client, account_id, ivan, incoming=True, amount="5000.00", settlement="transit")
    await _move(client, account_id, olga, incoming=False, amount="5000.00", settlement="transit")

    rows = {row["name"]: row for row in (await client.get("/settlements")).json()}
    assert money(rows["Иван"]["received"]) == Decimal("5000.00")
    assert money(rows["Ольга"]["given"]) == Decimal("5000.00")
    # Ни один не должен, и ни одному не должны.
    assert money(rows["Иван"]["balance"]) == Decimal("0")
    assert money(rows["Ольга"]["balance"]) == Decimal("0")


async def test_transit_is_not_earnings(client: AsyncClient, account_id):
    """Транзит меняет баланс счёта, но заработком не становится: иначе
    ставка за час и норма сбережений считались бы по чужим деньгам."""
    ivan = await _counterparty(client, "Иван")
    await _move(
        client, account_id, ivan, incoming=True, amount="5000.00", settlement="transit", date="2026-04-12"
    )

    summary = (
        await client.get("/dashboard/summary", params={"year": 2026, "month": 4, "range": "month"})
    ).json()
    assert money(summary["real_income"]) == Decimal("0")


async def test_a_purchase_on_someone_elses_money_keeps_its_category_but_not_the_spending(
    client: AsyncClient, account_id
):
    """Жена дала тысячу на продукты, он сходил и купил.

    Продукты куплены, чек есть, категория проставлена — но потратил он не
    свои деньги, и в его тратах этой тысячи быть не должно. Иначе выходит,
    что он купил продуктов себе, а норма сбережений считается по деньгам,
    которых он не зарабатывал.

    Пара движений: пришло от жены и ушло в магазин, оба «прошло через
    меня». Баланс счёта при этом меняется в обе стороны честно.
    """
    wife = await _counterparty(client, "Жена")
    groceries = (await client.get("/categories")).json()
    groceries_id = next(row["id"] for row in groceries if row["name"] == "Groceries")

    await _move(
        client, account_id, wife, incoming=True, amount="1000.00", settlement="transit", date="2026-04-05"
    )
    spend = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "external_out",
            "amount": "1000.00",
            "description": "Продукты на деньги жены",
            "date": "2026-04-05",
            "counterparty_id": wife,
            "settlement_kind": "transit",
            # Категория у внешнего движения разрешена: она нужна, чтобы
            # найти покупку потом, а не чтобы попасть в отчёт.
            "category_id": groceries_id,
        },
    )
    assert spend.status_code == 201, spend.text
    assert spend.json()["category"]["name"] == "Groceries"

    summary = (
        await client.get("/dashboard/summary", params={"year": 2026, "month": 4, "range": "month"})
    ).json()
    assert money(summary["real_income"]) == Decimal("0")
    assert money(summary["spent"]) == Decimal("0")
    # И в круге категорий её тоже нет: это не его трата.
    assert summary["spending_by_category"] == []

    # Зато в списке она находится по категории — ради этого категория там и
    # стоит.
    listing = (await client.get("/transactions", params={"category_id": groceries_id})).json()["items"]
    assert [row["description"] for row in listing] == ["Продукты на деньги жены"]
