"""Подстановка количества и единицы из прошлой покупки.

Хлеб берут по одной штуке, молоко по литру. Вводить одно и то же число в
каждом чеке человек будет ровно до тех пор, пока не перестанет заполнять
чек вообще.

Единица последней покупки важнее записанной в справочнике: в справочнике
лежит обычная мера товара, а чек заполняют по чеку.
"""
from httpx import AsyncClient


async def _product(client: AsyncClient, name: str, unit_id: int | None = None) -> dict:
    resp = await client.post(
        "/products", json={"name": name, "unit_id": unit_id, "barcode": None, "notes": None}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _unit(client: AsyncClient, name: str) -> dict:
    units = (await client.get("/units")).json()
    return next(unit for unit in units if unit["name"] == name)


async def _receipt(client: AsyncClient, account_id: int, items: list[dict]) -> None:
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "500.00",
            "description": "Магазин",
            "date": "2026-03-05",
            "items": items,
        },
    )
    assert resp.status_code == 201, resp.text


async def _read(client: AsyncClient, product_id: int) -> dict:
    rows = (await client.get("/products")).json()
    return next(row for row in rows if row["id"] == product_id)


async def test_a_never_bought_product_has_nothing_to_offer(client: AsyncClient):
    bread = await _product(client, "Хлеб")
    row = await _read(client, bread["id"])
    assert row["last_quantity"] is None
    assert row["last_unit_id"] is None


async def test_the_last_quantity_and_unit_are_remembered(client: AsyncClient, account_id: int):
    piece = await _unit(client, "шт")
    bread = await _product(client, "Хлеб")
    await _receipt(
        client, account_id, [{"name": "Хлеб", "product_id": bread["id"], "quantity": "2", "unit_id": piece["id"]}]
    )

    row = await _read(client, bread["id"])
    assert row["last_quantity"] == "2.0000"
    assert row["last_unit_id"] == piece["id"]


async def test_the_newest_purchase_wins(client: AsyncClient, account_id: int):
    piece = await _unit(client, "шт")
    bread = await _product(client, "Хлеб")
    for quantity, date in (("1", "2026-03-01"), ("3", "2026-03-09")):
        resp = await client.post(
            "/transactions",
            json={
                "account_id": account_id,
                "type": "expense",
                "amount": "100.00",
                "description": "Магазин",
                "date": date,
                "items": [
                    {"name": "Хлеб", "product_id": bread["id"], "quantity": quantity, "unit_id": piece["id"]}
                ],
            },
        )
        assert resp.status_code == 201, resp.text

    row = await _read(client, bread["id"])
    assert row["last_quantity"] == "3.0000"


async def test_an_empty_quantity_does_not_erase_what_was_known(client: AsyncClient, account_id: int):
    """«Не помню, сколько было» не должно стирать то, что помнили раньше."""
    piece = await _unit(client, "шт")
    bread = await _product(client, "Хлеб")
    await _receipt(
        client, account_id, [{"name": "Хлеб", "product_id": bread["id"], "quantity": "2", "unit_id": piece["id"]}]
    )
    await _receipt(client, account_id, [{"name": "Хлеб", "product_id": bread["id"]}])

    row = await _read(client, bread["id"])
    assert row["last_quantity"] == "2.0000"
    assert row["last_unit_id"] == piece["id"]
