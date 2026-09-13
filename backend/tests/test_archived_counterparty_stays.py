"""Человек в архиве остаётся в своих операциях — и в копии базы.

Архив не удаление. Он убирает запись из подстановки при вводе новых
операций, но операции, где человек уже стоит, обязаны помнить его: иначе
«отправить в архив» молча переписывало бы историю расчётов.

Интерфейс это обещание нарушал только на вид: открытая операция показывала
пустое поле, потому что в списке выбора были одни действующие записи. Здесь
проверяется, что за этим видом ничего не терялось на самом деле.
"""
from decimal import Decimal

from httpx import AsyncClient


async def _setup(client: AsyncClient) -> tuple[dict, dict, dict]:
    account = (
        await client.post("/accounts", json={"name": "Карта", "kind": "checking"})
    ).json()
    person = (await client.post("/counterparties", json={"name": "Человек"})).json()
    tx = await client.post(
        "/transactions",
        json={
            "account_id": account["id"],
            "type": "external_out",
            "amount": "700.00",
            "date": "2026-03-05",
            "counterparty_id": person["id"],
            "settlement_kind": "loan_out",
        },
    )
    assert tx.status_code == 201, tx.text
    return account, person, tx.json()


async def _archive(client: AsyncClient, person: dict) -> None:
    resp = await client.patch(f"/counterparties/{person['id']}", json={"is_archived": True})
    assert resp.status_code == 200, resp.text


async def _reread(client: AsyncClient, tx_id: int) -> dict:
    return next(row for row in (await client.get("/transactions")).json()["items"] if row["id"] == tx_id)


async def test_archiving_a_person_keeps_them_on_the_transaction(client: AsyncClient):
    _, person, tx = await _setup(client)

    await _archive(client, person)

    assert (await _reread(client, tx["id"]))["counterparty_id"] == person["id"]
    # И долг никуда не делся: архив — не прощение.
    settlements = {row["name"]: row for row in (await client.get("/settlements")).json()}
    assert Decimal(settlements["Человек"]["owed_to_me"]) == Decimal("700.00")


async def test_saving_the_form_unchanged_keeps_the_archived_person(client: AsyncClient):
    """Форма отправляет номер, который в ней был, — даже когда поле выглядело
    пустым. «Сохранить» человека не стирает."""
    _, person, tx = await _setup(client)
    await _archive(client, person)

    resp = await client.patch(
        f"/transactions/{tx['id']}",
        json={"description": "Правка", "counterparty_id": person["id"]},
    )
    assert resp.status_code == 200, resp.text
    assert (await _reread(client, tx["id"]))["counterparty_id"] == person["id"]


async def test_the_archived_person_survives_a_backup_round_trip(client: AsyncClient):
    """В копию уходят все записи справочника, с пометкой архива, и после
    восстановления операция указывает на того же человека."""
    _, person, tx = await _setup(client)
    await _archive(client, person)

    backup = (await client.get("/backup/export")).json()
    archived = next(row for row in backup["counterparties"] if row["id"] == person["id"])
    assert archived["is_archived"] is True

    assert (await client.post("/backup/import", json=backup)).status_code == 200

    restored = await _reread(client, tx["id"])
    assert restored["counterparty_id"] == person["id"]
    everyone = (await client.get("/counterparties?include_archived=true")).json()
    assert next(row for row in everyone if row["id"] == person["id"])["is_archived"] is True
