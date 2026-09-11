"""Транзит по каждому человеку отдельно.

Транзит — деньги, прошедшие через счёт насквозь: человек передал на
покупки, я купил. Долгом это не становится, и в оборот с человеком не
попадает: получил от одного, передал другому — иначе список читался бы как
«один щедрый, вторая просила».

Но общей суммы по всем сразу мало. Когда не сходится, нужно знать, с кем
именно: кто передал больше, чем потрачено, а на кого потрачено сверх
переданного.
"""
from httpx import AsyncClient


async def _counterparty(client: AsyncClient, name: str) -> dict:
    resp = await client.post("/counterparties", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _settlement(
    client: AsyncClient, account_id: int, counterparty_id: int, kind: str, direction: str, amount: str
) -> None:
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": direction,
            "amount": amount,
            "description": "Расчёт",
            "date": "2026-03-05",
            "counterparty_id": counterparty_id,
            "settlement_kind": kind,
        },
    )
    assert resp.status_code == 201, resp.text


async def _row(client: AsyncClient, name: str) -> dict:
    rows = (await client.get("/settlements")).json()
    return next(row for row in rows if row["name"] == name)


async def test_money_left_over_is_positive(client: AsyncClient, account_id: int):
    """Передал тысячу, потрачено семьсот — три сотни его денег у вас."""
    person = await _counterparty(client, "Жена")
    await _settlement(client, account_id, person["id"], "transit", "external_in", "1000.00")
    await _settlement(client, account_id, person["id"], "transit", "external_out", "700.00")

    row = await _row(client, "Жена")
    assert row["transit_in"] == "1000.00"
    assert row["transit_out"] == "700.00"
    assert row["transit_balance"] == "300.00"


async def test_spending_beyond_what_was_sent_is_negative(client: AsyncClient, account_id: int):
    """Потрачено больше переданного — разницу вложили свою."""
    person = await _counterparty(client, "Мама")
    await _settlement(client, account_id, person["id"], "transit", "external_in", "500.00")
    await _settlement(client, account_id, person["id"], "transit", "external_out", "870.00")

    row = await _row(client, "Мама")
    assert row["transit_balance"] == "-370.00"


async def test_transit_stays_out_of_the_debt(client: AsyncClient, account_id: int):
    """Главное: транзит не делает никого должником. Именно поэтому рядом с
    ненулевым транзитом по-прежнему написано «рассчитались»."""
    person = await _counterparty(client, "Брат")
    await _settlement(client, account_id, person["id"], "transit", "external_in", "4500.00")
    await _settlement(client, account_id, person["id"], "transit", "external_out", "4870.00")

    row = await _row(client, "Брат")
    assert row["balance"] == "0.00"
    assert row["owed_to_me"] == "0.00"
    assert row["owed_by_me"] == "0.00"


async def test_transit_stays_out_of_the_turnover(client: AsyncClient, account_id: int):
    """Оборот с человеком — то, что действительно между вами прошло.
    Чужие деньги, полежавшие на счёте, туда не входят."""
    person = await _counterparty(client, "Сергей")
    await _settlement(client, account_id, person["id"], "transit", "external_in", "4500.00")
    await _settlement(client, account_id, person["id"], "gift", "external_out", "300.00")

    row = await _row(client, "Сергей")
    assert row["received"] == "0.00"
    assert row["given"] == "300.00"
    assert row["transit_in"] == "4500.00"


async def test_a_person_with_only_transit_still_appears(client: AsyncClient, account_id: int):
    """Раньше такой человек в списке не показывался вовсе: транзит
    пропускался до создания строки."""
    person = await _counterparty(client, "Сосед")
    await _settlement(client, account_id, person["id"], "transit", "external_in", "200.00")

    rows = (await client.get("/settlements")).json()
    assert any(row["name"] == "Сосед" for row in rows)


async def test_loans_are_unaffected(client: AsyncClient, account_id: int):
    """Долг считается по-прежнему и с транзитом не смешивается."""
    person = await _counterparty(client, "Коллега")
    await _settlement(client, account_id, person["id"], "loan_out", "external_out", "1000.00")
    await _settlement(client, account_id, person["id"], "transit", "external_in", "300.00")

    row = await _row(client, "Коллега")
    assert row["balance"] == "1000.00"
    assert row["transit_balance"] == "300.00"
