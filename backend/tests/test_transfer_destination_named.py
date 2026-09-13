"""Перевод отдаёт счёт получателя целиком, а не одним номером.

Интерфейс подписывает перевод маршрутом «откуда → куда». По одному номеру
имя пришлось бы искать в списке счетов, а список по умолчанию без архивных:
перевод на закрытую карту остался бы без подписи — ровно тогда, когда
вспомнить, куда ушли деньги, труднее всего.
"""
from httpx import AsyncClient


async def _account(client: AsyncClient, name: str, opening: str = "0") -> dict:
    resp = await client.post(
        "/accounts", json={"name": name, "kind": "checking", "opening_balance": opening}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _transfer(client: AsyncClient, source: dict, target: dict) -> dict:
    resp = await client.post(
        "/transactions",
        json={
            "account_id": source["id"],
            "transfer_account_id": target["id"],
            "type": "transfer",
            "amount": "500.00",
            "date": "2026-03-05",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_a_transfer_names_its_destination(client: AsyncClient):
    source = await _account(client, "Откуда", "1000")
    target = await _account(client, "Куда")

    created = await _transfer(client, source, target)

    # И в ответе на создание, и в списке: интерфейс рисует строку сразу
    # после сохранения, не дожидаясь перечитывания.
    assert created["transfer_account"]["name"] == "Куда"
    listed = next(
        row for row in (await client.get("/transactions")).json()["items"] if row["id"] == created["id"]
    )
    assert listed["transfer_account"]["name"] == "Куда"


async def test_an_ordinary_expense_has_no_destination(client: AsyncClient):
    account = await _account(client, "Карта")
    resp = await client.post(
        "/transactions",
        json={"account_id": account["id"], "type": "expense", "amount": "100.00", "date": "2026-03-05"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["transfer_account"] is None


async def test_the_destination_is_named_even_after_archiving(client: AsyncClient):
    """Архивный счёт пропадает из списка счетов, но не из истории переводов."""
    source = await _account(client, "Откуда", "1000")
    target = await _account(client, "Закрытая карта")
    created = await _transfer(client, source, target)

    resp = await client.patch(f"/accounts/{target['id']}", json={"is_archived": True})
    assert resp.status_code == 200, resp.text

    listed = next(
        row for row in (await client.get("/transactions")).json()["items"] if row["id"] == created["id"]
    )
    assert listed["transfer_account"]["name"] == "Закрытая карта"
