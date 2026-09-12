"""Отбор операций по человеку.

Вопрос «сколько я ему передал и когда» задают не сводке, а списку: в сводке
одно число, а разговаривать с человеком приходится про конкретные даты и
описания. Раньше такие операции искали глазами по месяцам.

Обе стороны транзита считаются участием: деньги брата, переданные маме,
стоят у мамы в контрагентах и у брата во второй стороне, и отбор по одной
колонке показал бы половину истории — ровно ту половину, которой не хватает,
когда речь о долге.
"""
from httpx import AsyncClient


async def _person(client: AsyncClient, name: str) -> dict:
    resp = await client.post("/counterparties", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _settlement(
    client: AsyncClient,
    account_id: int,
    *,
    incoming: bool,
    amount: str,
    counterparty_id: int,
    settlement_kind: str = "loan_out",
    transit_party_id: int | None = None,
    description: str = "Расчёт",
) -> None:
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "external_in" if incoming else "external_out",
            "amount": amount,
            "description": description,
            "date": "2026-03-05",
            "counterparty_id": counterparty_id,
            "transit_party_id": transit_party_id,
            "settlement_kind": settlement_kind,
        },
    )
    assert resp.status_code == 201, resp.text


async def _total(client: AsyncClient, **params) -> int:
    resp = await client.get("/transactions", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["total"]


async def test_transactions_can_be_narrowed_to_one_person(client: AsyncClient, account_id: int):
    brother = await _person(client, "Брат")
    friend = await _person(client, "Друг")

    await _settlement(
        client, account_id, incoming=False, amount="5000.00",
        counterparty_id=brother["id"], description="Занял до зарплаты",
    )
    await _settlement(
        client, account_id, incoming=False, amount="700.00", counterparty_id=friend["id"]
    )

    assert await _total(client, counterparty_id=brother["id"]) == 1
    assert await _total(client, counterparty_id=friend["id"]) == 1
    # Без отбора видны обе — иначе фильтр ничего бы и не значил.
    assert await _total(client) == 2


async def test_the_filter_works_together_with_the_type(client: AsyncClient, account_id: int):
    """В интерфейсе человек появляется только у расчётов, и сузить список
    одновременно по виду и по человеку — обычный случай."""
    brother = await _person(client, "Брат")
    await _settlement(
        client, account_id, incoming=False, amount="5000.00", counterparty_id=brother["id"]
    )
    await _settlement(
        client, account_id, incoming=True, amount="2000.00",
        counterparty_id=brother["id"], settlement_kind="repayment",
    )

    assert await _total(client, counterparty_id=brother["id"]) == 2
    assert await _total(client, counterparty_id=brother["id"], type="external_out") == 1
    assert await _total(client, counterparty_id=brother["id"], type="external_in") == 1


async def test_both_sides_of_a_transit_count_as_the_person(client: AsyncClient, account_id: int):
    """Брат дал 4 500, я отдал их маме. Операция расхода стоит на маме, но и
    к брату относится: это его деньги."""
    brother = await _person(client, "Брат")
    mother = await _person(client, "Мама")

    await _settlement(
        client, account_id, incoming=True, amount="4500.00",
        counterparty_id=brother["id"], settlement_kind="transit",
    )
    await _settlement(
        client, account_id, incoming=False, amount="4500.00",
        counterparty_id=mother["id"], transit_party_id=brother["id"],
        settlement_kind="transit",
    )

    # Обе: и приход от брата, и расход его деньгами.
    assert await _total(client, counterparty_id=brother["id"]) == 2
    # У мамы — только та, где деньги дошли до неё.
    assert await _total(client, counterparty_id=mother["id"]) == 1
