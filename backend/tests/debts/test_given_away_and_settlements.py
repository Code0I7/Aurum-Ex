"""Отданное безвозвратно — трата; одолженное людям — часть капитала.

Две стороны одного правила. Деньги, ушедшие к человеку, либо вернутся — и
тогда они остаются вашими, хоть и лежат не у вас, — либо не вернутся, и
тогда это трата, такая же, как покупка. Раньше ни то ни другое не
учитывалось: отданное насовсем не попадало в расход, а одолженное
пропадало из капитала.
"""
from decimal import Decimal

from httpx import AsyncClient

from tests.helpers import money, txn_payload


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
    date: str = "2026-03-10",
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


async def _summary(client: AsyncClient, year: int = 2026, month: int = 3) -> dict:
    resp = await client.get(
        "/dashboard/summary", params={"year": year, "month": month, "range": "month"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _net_worth(client: AsyncClient) -> dict:
    resp = await client.get("/net-worth/summary", params={"range": "all"})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_money_given_away_is_spending(client: AsyncClient, account_id, categories):
    """Отдал — значит потратил.

    Требования не осталось, вернуть нечего. Норма сбережений обязана это
    видеть: иначе заработавший сто тысяч и отдавший девяносто сохранил,
    по мнению приложения, всё до копейки.
    """
    friend = await _counterparty(client, "Иван")
    await client.post(
        "/transactions",
        json=txn_payload(
            account_id, amount="100000.00", type="income",
            category_id=categories["Salary"]["id"], date="2026-03-01",
        ),
    )
    await _move(client, account_id, friend, incoming=False, amount="90000.00", settlement="gift")

    body = await _summary(client)
    assert money(body["real_income"]) == Decimal("100000.00")
    assert money(body["spent"]) == Decimal("90000.00")
    assert money(body["net"]) == Decimal("10000.00")


async def test_money_lent_is_spending_too(client: AsyncClient, account_id, categories):
    """Дал в долг — денег на счёте нет, и отчёт обязан это сказать.

    Требование к человеку активом не считается, значит сумма ушла. Иначе
    «Итог за период» говорил бы «сохранено» в месяце, когда денег стало
    на пятьдесят тысяч меньше.
    """
    friend = await _counterparty(client, "Ольга")
    await _move(client, account_id, friend, incoming=False, amount="50000.00", settlement="loan_out")

    body = await _summary(client)
    assert money(body["spent"]) == Decimal("50000.00")
    assert money(body["to_people"]) == Decimal("50000.00")


async def test_repayment_lowers_the_spending_it_came_back_to(
    client: AsyncClient, account_id, categories
):
    """Вернувшийся долг уменьшает расход.

    Деньги пришли обратно, и не заметить этого нельзя: иначе итог остался
    бы занижен навсегда. За полный круг «дал и вернули» выходит ноль.
    """
    friend = await _counterparty(client, "Ольга")
    await _move(client, account_id, friend, incoming=False, amount="50000.00", settlement="loan_out")
    await _move(
        client, account_id, friend, incoming=True, amount="20000.00",
        settlement="repayment", date="2026-03-25",
    )

    body = await _summary(client)
    assert money(body["spent"]) == Decimal("30000.00")
    assert money(body["to_people"]) == Decimal("30000.00")


async def test_borrowing_and_paying_it_back_nets_to_nothing(
    client: AsyncClient, account_id, categories
):
    """Занял и вернул — расход не изменился: деньги прошли туда и обратно."""
    friend = await _counterparty(client, "Пётр")
    await _move(client, account_id, friend, incoming=True, amount="15000.00", settlement="loan_in")
    await _move(
        client, account_id, friend, incoming=False, amount="15000.00",
        settlement="repayment", date="2026-03-28",
    )

    body = await _summary(client)
    assert money(body["spent"]) == Decimal("0")


async def test_given_away_is_named_apart_from_purchases(
    client: AsyncClient, account_id, categories
):
    """Отданное входит в расход, но статьи у него нет.

    Поэтому оно названо отдельным числом, а доли круга по категориям
    считаются от покупок: иначе они не складывались бы в сто процентов.
    """
    friend = await _counterparty(client, "Иван")
    await client.post(
        "/transactions",
        json=txn_payload(
            account_id, amount="1000.00",
            category_id=categories["Groceries"]["id"], date="2026-03-05",
        ),
    )
    await _move(client, account_id, friend, incoming=False, amount="4000.00", settlement="gift")

    body = await _summary(client)
    assert money(body["spent"]) == Decimal("5000.00")
    assert money(body["to_people"]) == Decimal("4000.00")
    # Круг показывает только покупки, и его доли считаются от них.
    shares = {item["name"]: item for item in body["spending_by_category"]}
    assert money(shares["Groceries"]["amount"]) == Decimal("1000.00")
    assert shares["Groceries"]["percent"] == 100.0


async def test_transit_moves_neither_spending_nor_capital(
    client: AsyncClient, account_id, categories
):
    """Чужие деньги, прошедшие насквозь, не трата и не капитал."""
    friend = await _counterparty(client, "Пётр")
    await _move(client, account_id, friend, incoming=True, amount="3000.00", settlement="transit")
    await _move(client, account_id, friend, incoming=False, amount="3000.00", settlement="transit")

    body = await _summary(client)
    assert money(body["spent"]) == Decimal("0")
    assert money(body["to_people"]) == Decimal("0")
    before_capital = money((await _net_worth(client))["current"])
    assert before_capital == Decimal("0")


async def test_lending_lowers_capital_like_any_money_that_left(
    client: AsyncClient, account_id, categories
):
    """Одолженное человеку из капитала уходит.

    Требование к нему активом не считается: у вклада есть хоть какая-то
    гарантия возврата, у одолженной тысячи никакой — вернуть могут через
    год, а могут не вернуть вовсе. Сколько и кому должны, видно на вкладке
    долгов; капитал остаётся тем, что действительно есть.
    """
    friend = await _counterparty(client, "Ольга")
    await client.post(
        "/transactions",
        json=txn_payload(
            account_id, amount="60000.00", type="income",
            category_id=categories["Salary"]["id"], date="2026-03-01",
        ),
    )
    before = await _net_worth(client)
    await _move(client, account_id, friend, incoming=False, amount="20000.00", settlement="loan_out")
    after = await _net_worth(client)

    assert money(after["current"]) == money(before["current"]) - Decimal("20000.00")
    assert money(after["liquid"]) == money(before["liquid"]) - Decimal("20000.00")


async def test_repayment_brings_the_money_back(client: AsyncClient, account_id, categories):
    """Вернули долг — деньги снова на счёте, и капитал это видит."""
    friend = await _counterparty(client, "Ольга")
    await client.post(
        "/transactions",
        json=txn_payload(
            account_id, amount="60000.00", type="income",
            category_id=categories["Salary"]["id"], date="2026-03-01",
        ),
    )
    await _move(client, account_id, friend, incoming=False, amount="20000.00", settlement="loan_out")
    lent = await _net_worth(client)
    await _move(
        client, account_id, friend, incoming=True, amount="20000.00",
        settlement="repayment", date="2026-03-20",
    )
    repaid = await _net_worth(client)

    assert money(repaid["current"]) == money(lent["current"]) + Decimal("20000.00")
    assert money(repaid["liquid"]) == money(lent["liquid"]) + Decimal("20000.00")


async def test_the_debts_tab_still_remembers_who_owes(client: AsyncClient, account_id, categories):
    """Из капитала долг ушёл, но не из учёта: напомнить человеку по-прежнему
    есть чем, и ради этого запись и держат."""
    friend = await _counterparty(client, "Ольга")
    await _move(client, account_id, friend, incoming=False, amount="20000.00", settlement="loan_out")

    resp = await client.get("/settlements/summary")
    assert resp.status_code == 200, resp.text
    assert money(resp.json()["owed_to_me"]) == Decimal("20000.00")


async def test_a_gift_given_lowers_capital(client: AsyncClient, account_id, categories):
    """Подаренное уходит из капитала — как и всё, что ушло со счёта."""
    friend = await _counterparty(client, "Иван")
    await client.post(
        "/transactions",
        json=txn_payload(
            account_id, amount="60000.00", type="income",
            category_id=categories["Salary"]["id"], date="2026-03-01",
        ),
    )
    before = await _net_worth(client)
    await _move(client, account_id, friend, incoming=False, amount="5000.00", settlement="gift")
    after = await _net_worth(client)

    assert money(after["current"]) == money(before["current"]) - Decimal("5000.00")


async def test_cash_flow_counts_everything_that_went_to_people(
    client: AsyncClient, account_id, categories
):
    """Страница движения денег считает расход тем же правилом, что и обзор:
    два разных ответа на один вопрос — худшее, что приложение может
    показать про деньги."""
    friend = await _counterparty(client, "Иван")
    await _move(client, account_id, friend, incoming=False, amount="2500.00", settlement="gift")
    await _move(client, account_id, friend, incoming=False, amount="7000.00", settlement="loan_out")

    resp = await client.get("/cash-flow", params={"start_date": "2026-03-01", "end_date": "2026-03-31"})
    body = resp.json()
    assert money(body["total_expense"]) == Decimal("9500.00")
async def test_the_choice_can_be_switched_off(client: AsyncClient, account_id, categories):
    """Долг тратой считать необязательно — это настройка.

    Правильного ответа нет: деньги со счёта ушли, но вернутся. Выключено —
    долг уходит из расхода, а сколько его ушло, остаётся названным
    отдельным числом: разрыв между итогом и деньгами никуда не девается, и
    промолчать о нём было бы хуже, чем назвать.
    """
    friend = await _counterparty(client, "Ольга")
    await client.post(
        "/transactions",
        json=txn_payload(
            account_id, amount="1000.00",
            category_id=categories["Groceries"]["id"], date="2026-03-05",
        ),
    )
    await _move(client, account_id, friend, incoming=False, amount="40000.00", settlement="loan_out")
    await _move(client, account_id, friend, incoming=False, amount="2000.00", settlement="gift")

    assert (await client.patch("/settings", json={"lending_is_spending": False})).status_code == 200
    body = await _summary(client)
    # Покупка и отданное насовсем — расход; долг — нет.
    assert money(body["spent"]) == Decimal("3000.00")
    assert money(body["to_people"]) == Decimal("2000.00")
    # Но названо, куда ушли остальные деньги.
    assert money(body["lent_net"]) == Decimal("40000.00")

    assert (await client.patch("/settings", json={"lending_is_spending": True})).status_code == 200
    body = await _summary(client)
    assert money(body["spent"]) == Decimal("43000.00")


async def test_the_switch_reaches_the_cash_flow_page_too(
    client: AsyncClient, account_id, categories
):
    """Обзор и движение денег обязаны отвечать одинаково при любом выборе."""
    friend = await _counterparty(client, "Ольга")
    await _move(client, account_id, friend, incoming=False, amount="40000.00", settlement="loan_out")

    assert (await client.patch("/settings", json={"lending_is_spending": False})).status_code == 200
    resp = await client.get("/cash-flow", params={"start_date": "2026-03-01", "end_date": "2026-03-31"})
    assert money(resp.json()["total_expense"]) == Decimal("0")

    assert (await client.patch("/settings", json={"lending_is_spending": True})).status_code == 200
    resp = await client.get("/cash-flow", params={"start_date": "2026-03-01", "end_date": "2026-03-31"})
    assert money(resp.json()["total_expense"]) == Decimal("40000.00")
