"""Позиция чека склеивается с товаром по названию.

Справочник товаров существует ради одного — кривой цены. Она строится
только по позициям с product_id, поэтому позиция, набранная текстом, для
неё не существует.

Выглядит это так: один и тот же товар лежит в трёх чеках, в справочнике
он заведён, а привязана оказалась одна позиция из трёх — в двух
остальных название просто напечатали заново. Подсказка есть,
но нажимают её не всегда, а печатают одно и то же.
"""
from httpx import AsyncClient


async def _product(client: AsyncClient, name: str, category_id: int | None = None) -> dict:
    resp = await client.post(
        "/products",
        json={"name": name, "category_id": category_id, "unit_id": None, "barcode": None, "notes": None},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _receipt(client: AsyncClient, account_id: int, items: list[dict]) -> dict:
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
    return resp.json()


async def test_a_typed_name_binds_to_an_existing_product(client: AsyncClient, account_id: int):
    bread = await _product(client, "Хлеб бородинский")
    created = await _receipt(client, account_id, [{"name": "Хлеб бородинский", "amount": "120.00"}])
    assert created["items"][0]["product_id"] == bread["id"]


async def test_binding_ignores_case_and_stray_spaces(client: AsyncClient, account_id: int):
    """Регистр и пробелы по краям — то, чем одно и то же название
    отличается от самого себя чаще всего."""
    bread = await _product(client, "Хлеб бородинский")
    created = await _receipt(client, account_id, [{"name": "  хлеб Бородинский ", "amount": "120.00"}])
    assert created["items"][0]["product_id"] == bread["id"]


async def test_the_typed_name_is_kept_as_written(client: AsyncClient, account_id: int):
    """Привязка не переписывает название: в магазине товар мог называться
    иначе, и это важно помнить."""
    await _product(client, "Хлеб бородинский")
    created = await _receipt(client, account_id, [{"name": "хлеб бородинский", "amount": "120.00"}])
    assert created["items"][0]["name"] == "хлеб бородинский"


async def test_a_different_product_is_not_glued_on(client: AsyncClient, account_id: int):
    """Только точное совпадение. «Молоко» и «Молоко 3,2%» — разные товары,
    и склейка по вхождению испортила бы цену за базовую меру у обоих."""
    await _product(client, "Молоко")
    created = await _receipt(client, account_id, [{"name": "Молоко 3,2%", "amount": "89.00"}])
    assert created["items"][0]["product_id"] is None


async def test_an_explicit_product_wins_over_the_name(client: AsyncClient, account_id: int):
    """Выбранный в подсказке товар не переопределяется поиском по имени:
    человек мог нарочно указать другой."""
    await _product(client, "Вода")
    sparkling = await _product(client, "Вода газированная")
    created = await _receipt(
        client, account_id, [{"name": "Вода", "product_id": sparkling["id"], "amount": "45.00"}]
    )
    assert created["items"][0]["product_id"] == sparkling["id"]


async def test_an_archived_product_does_not_come_back(client: AsyncClient, account_id: int):
    """Архив для того и нужен, чтобы товар перестал подставляться сам."""
    old = await _product(client, "Компот")
    assert (await client.patch(f"/products/{old['id']}", json={"is_archived": True})).status_code == 200
    created = await _receipt(client, account_id, [{"name": "Компот", "amount": "30.00"}])
    assert created["items"][0]["product_id"] is None


async def test_bound_lines_reach_the_price_curve(client: AsyncClient, account_id: int):
    """Ради этого всё и делается: три покупки — три точки, а не одна."""
    bread = await _product(client, "Хлеб бородинский")
    for amount in ("120.00", "125.00", "130.00"):
        await _receipt(client, account_id, [{"name": "Хлеб бородинский", "quantity": "1", "amount": amount}])

    history = (await client.get(f"/products/{bread['id']}/prices")).json()
    # Кривая одна: все три покупки записаны штуками.
    assert len(history["series"]) == 1
    assert len(history["series"][0]["points"]) == 3
