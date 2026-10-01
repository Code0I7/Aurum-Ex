"""Транзит раскладывается по тому, ЧЬИ это были деньги.

Транзит проходит между двумя людьми, а поле для человека в операции было
одно. Брат передал на покупки для мамы, покупки сделаны для мамы — в записи
оказывались брат у прихода и мама у расхода, и сложить их было не по чему.

Первая попытка считала по контрагенту и писала «брату осталось 4 500» и
«маме недодал 4 870». Вторая считала по тому, для кого деньги шли, и писала
маме те же 4 870 — а из них моих было только 370, остальное брата, и оно
уже дошло.

Поэтому ключ сложения — владелец денег. Чужое, прошедшее насквозь, гасится
у него самого, и у человека остаётся ровно то, что вы вложили своих.
"""
from httpx import AsyncClient


async def _person(client: AsyncClient, name: str) -> dict:
    resp = await client.post("/counterparties", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _transit(
    client: AsyncClient,
    account_id: int,
    *,
    incoming: bool,
    amount: str,
    counterparty_id: int,
    transit_party_id: int | None = None,
    date: str = "2026-03-05",
) -> None:
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "external_in" if incoming else "external_out",
            "amount": amount,
            "description": "Транзит",
            "date": date,
            "counterparty_id": counterparty_id,
            "transit_party_id": transit_party_id,
            "settlement_kind": "transit",
        },
    )
    assert resp.status_code == 201, resp.text


async def _rows(client: AsyncClient, query: str = "") -> dict:
    listing = (await client.get(f"/settlements/transit-by-person{query}")).json()
    return {row["name"]: row for row in listing}


async def test_someone_elses_money_cancels_out_on_its_owner(
    client: AsyncClient, account_id: int
):
    """Тот самый случай, ради которого всё и переделывалось.

    Брат дал 4 500, я отдал их маме и добавил 370 своих. С братом не
    осталось ничего — его деньги дошли; с мамой у меня минус 370, и это
    единственное число, которое здесь моё.
    """
    brother = await _person(client, "Брат")
    mother = await _person(client, "Мама")

    await _transit(client, account_id, incoming=True, amount="4500.00", counterparty_id=brother["id"])
    await _transit(
        client, account_id, incoming=False, amount="4500.00",
        counterparty_id=mother["id"], transit_party_id=brother["id"],
    )
    for amount in ("222.00", "148.00"):
        await _transit(
            client, account_id, incoming=False, amount=amount, counterparty_id=mother["id"]
        )

    rows = await _rows(client)
    assert rows["Брат"]["balance"] == "0.00"
    assert rows["Мама"]["received"] == "0.00"
    assert rows["Мама"]["spent"] == "370.00"
    assert rows["Мама"]["balance"] == "-370.00"


async def test_money_handed_over_for_a_third_person_lands_on_them(
    client: AsyncClient, account_id: int
):
    """Деньги могут быть не того, кто их передал: брат отдал мамины."""
    brother = await _person(client, "Брат")
    mother = await _person(client, "Мама")

    await _transit(
        client, account_id, incoming=True, amount="4500.00",
        counterparty_id=brother["id"], transit_party_id=mother["id"],
    )
    await _transit(client, account_id, incoming=False, amount="4870.00", counterparty_id=mother["id"])

    rows = await _rows(client)
    assert rows["Мама"]["received"] == "4500.00"
    assert rows["Мама"]["spent"] == "4870.00"
    assert rows["Мама"]["balance"] == "-370.00"
    # Брат только передал чужое: ни он никому не должен, ни ему.
    assert "Брат" not in rows


async def test_money_left_over_is_positive(client: AsyncClient, account_id: int):
    wife = await _person(client, "Жена")
    await _transit(client, account_id, incoming=True, amount="1000.00", counterparty_id=wife["id"])
    await _transit(client, account_id, incoming=False, amount="700.00", counterparty_id=wife["id"])

    rows = await _rows(client)
    assert rows["Жена"]["balance"] == "300.00"


async def test_several_sources_add_up_on_one_person(client: AsyncClient, account_id: int):
    """Входов может быть несколько — это и было главным вопросом к схеме."""
    brother = await _person(client, "Брат")
    sister = await _person(client, "Сестра")
    mother = await _person(client, "Мама")

    for source, amount in ((brother, "2000.00"), (sister, "1500.00")):
        await _transit(
            client, account_id, incoming=True, amount=amount,
            counterparty_id=source["id"], transit_party_id=mother["id"],
        )
    await _transit(client, account_id, incoming=False, amount="3000.00", counterparty_id=mother["id"])

    rows = await _rows(client)
    assert rows["Мама"]["received"] == "3500.00"
    assert rows["Мама"]["balance"] == "500.00"
    assert rows["Мама"]["operations"] == 3
    assert "Брат" not in rows and "Сестра" not in rows


async def test_an_incoming_without_an_owner_belongs_to_whoever_handed_it_over(
    client: AsyncClient, account_id: int
):
    """Пустое поле у прихода — самый частый случай: деньги дал их владелец.

    Заполнять его ради этого не нужно, и молчание не должно ронять строку.
    """
    brother = await _person(client, "Брат")
    await _transit(client, account_id, incoming=True, amount="1000.00", counterparty_id=brother["id"])

    rows = await _rows(client)
    assert rows["Брат"]["received"] == "1000.00"
    assert rows["Брат"]["balance"] == "1000.00"


async def test_the_period_can_be_narrowed(client: AsyncClient, account_id: int):
    mother = await _person(client, "Мама")
    await _transit(
        client, account_id, incoming=True, amount="1000.00",
        counterparty_id=mother["id"], date="2026-01-10",
    )
    await _transit(
        client, account_id, incoming=False, amount="400.00",
        counterparty_id=mother["id"], date="2026-03-10",
    )

    whole_year = await _rows(client, "?year=2026")
    assert whole_year["Мама"]["balance"] == "600.00"

    january = await _rows(client, "?year=2026&month=1")
    assert january["Мама"]["received"] == "1000.00"
    assert january["Мама"]["spent"] == "0.00"


async def test_transit_still_creates_no_debt(client: AsyncClient, account_id: int):
    """Разделение сторон ничего не изменило в главном: транзит не делает
    никого должником."""
    brother = await _person(client, "Брат")
    mother = await _person(client, "Мама")
    await _transit(client, account_id, incoming=True, amount="4500.00", counterparty_id=brother["id"])
    await _transit(
        client, account_id, incoming=False, amount="4870.00",
        counterparty_id=mother["id"], transit_party_id=brother["id"],
    )

    summary = (await client.get("/settlements/summary")).json()
    assert summary["owed_to_me"] == "0.00"
    assert summary["owed_by_me"] == "0.00"
