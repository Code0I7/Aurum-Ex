"""Справочник товаров, позиции чека и динамика цен.

Десять чеков со словом «хлеб» — десять несвязанных строк. Десять позиций,
указывающих на одну строку справочника, — кривая цены. Разница между
«динамика цен работает» и «не работает» ровно в этом.

Приведение к базовой единице — вторая половина того же: без коэффициента
«1,5 л за 120 ₽» и «500 мл за 55 ₽» несравнимы, и в исходной таблице колонки
количества пустовали в 89% записей, потому что единицы там были подписями
без арифметики.
"""
from decimal import Decimal

from httpx import AsyncClient


async def _units(client: AsyncClient) -> dict[str, dict]:
    return {row["name"]: row for row in (await client.get("/units")).json()}


async def _product(client: AsyncClient, name: str, **overrides) -> dict:
    payload = {"name": name}
    payload.update(overrides)
    resp = await client.post("/products", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _receipt(client: AsyncClient, account_id: int, categories, items: list[dict], amount: str, date: str) -> dict:
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": amount,
            "description": "Магазин",
            "date": date,
            "category_id": categories["Groceries"]["id"],
            "items": items,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_a_product_name_cannot_be_duplicated(client: AsyncClient):
    """Два «Хлеб чёрный» разорвали бы кривую цены надвое, и ни одна из
    половин не была бы правдой."""
    await _product(client, "Хлеб чёрный")
    resp = await client.post("/products", json={"name": "хлеб чёрный"})
    assert resp.status_code == 400


async def test_a_receipt_can_be_itemised(client: AsyncClient, account_id, categories):
    bread = await _product(client, "Хлеб чёрный")
    milk = await _product(client, "Молоко 3.2%")

    receipt = await _receipt(
        client,
        account_id,
        categories,
        [
            {"product_id": bread["id"], "name": "Хлеб городской", "price": "45.00", "quantity": "2"},
            {"product_id": milk["id"], "name": "Молоко", "price": "89.00", "quantity": "1"},
        ],
        amount="224.00",
        date="2026-03-01",
    )

    assert len(receipt["items"]) == 2
    # Название из чека сохраняется своё, даже когда товар выбран из
    # справочника: в магазине он мог называться иначе.
    assert receipt["items"][0]["name"] == "Хлеб городской"
    # Сумма позиции посчиталась сама из цены и количества.
    assert Decimal(receipt["items"][0]["amount"]) == Decimal("90")
    assert receipt["items"][0]["position"] == 0
    assert receipt["items"][1]["position"] == 1


async def test_items_need_not_add_up_to_the_transaction(client: AsyncClient, account_id, categories):
    """Помнить, что купили хлеб, не помня остального, — обычное дело.
    Сумма транзакции остаётся источником истины."""
    receipt = await _receipt(
        client,
        account_id,
        categories,
        [{"name": "Хлеб", "price": "45.00", "quantity": "1"}],
        amount="1500.00",
        date="2026-03-01",
    )
    assert Decimal(receipt["amount"]) == Decimal("1500")
    assert Decimal(receipt["items"][0]["amount"]) == Decimal("45")


async def test_an_item_without_a_price_is_still_stored(client: AsyncClient, account_id, categories):
    """Позиция без цены — воспоминание, а не измерение. Отказ такое хранить
    потерял бы память целиком."""
    receipt = await _receipt(
        client,
        account_id,
        categories,
        [{"name": "Что-то ещё"}],
        amount="300.00",
        date="2026-03-01",
    )
    assert receipt["items"][0]["amount"] is None
    assert receipt["items"][0]["price"] is None


async def test_a_receipt_with_no_items_is_valid(client: AsyncClient, account_id, categories):
    """Быстрый ввод остаётся одним действием."""
    receipt = await _receipt(client, account_id, categories, [], amount="300.00", date="2026-03-01")
    assert receipt["items"] == []


async def test_editing_replaces_the_whole_basket(client: AsyncClient, account_id, categories):
    """Правка чека — переписывание его состава, а не дописывание строк."""
    receipt = await _receipt(
        client,
        account_id,
        categories,
        [{"name": "Хлеб", "price": "45.00", "quantity": "1"}],
        amount="300.00",
        date="2026-03-01",
    )
    resp = await client.patch(
        f"/transactions/{receipt['id']}",
        json={"items": [{"name": "Молоко", "price": "89.00", "quantity": "1"}]},
    )
    assert resp.status_code == 200, resp.text
    assert [item["name"] for item in resp.json()["items"]] == ["Молоко"]

    # Пустой список стирает состав, а None его не трогает.
    resp = await client.patch(f"/transactions/{receipt['id']}", json={"items": []})
    assert resp.json()["items"] == []
    resp = await client.patch(f"/transactions/{receipt['id']}", json={"description": "Магазин у дома"})
    assert resp.json()["items"] == []


async def test_price_history_compares_litres_with_millilitres(client: AsyncClient, account_id, categories):
    """1,5 л за 120 ₽ и 500 мл за 55 ₽ становятся сравнимы только после
    приведения к базовой единице. Ради этого у единиц есть коэффициент."""
    units = await _units(client)
    litre = units["л"]
    millilitre = units["мл"]
    juice = await _product(client, "Сок яблочный", unit_id=litre["id"])

    await _receipt(
        client,
        account_id,
        categories,
        [{"product_id": juice["id"], "name": "Сок 1.5л", "quantity": "1.5", "unit_id": litre["id"], "amount": "120.00"}],
        amount="120.00",
        date="2026-03-01",
    )
    await _receipt(
        client,
        account_id,
        categories,
        [{"product_id": juice["id"], "name": "Сок 0.5л", "quantity": "500", "unit_id": millilitre["id"], "amount": "55.00"}],
        amount="55.00",
        date="2026-04-01",
    )

    history = (await client.get(f"/products/{juice['id']}/prices")).json()
    assert len(history["points"]) == 2
    # Базовая мера — литр, а не миллилитр: «0,08 за миллилитр»
    # арифметически верно и бесполезно, в магазине сравнивают рубли за литр.
    # 120 / (1,5 × 1) = 80 ₽ за литр; 55 / (500 × 0,001) = 110.
    assert Decimal(history["points"][0]["price_per_base_unit"]).quantize(Decimal("0.01")) == Decimal("80.00")
    assert Decimal(history["points"][1]["price_per_base_unit"]).quantize(Decimal("0.01")) == Decimal("110.00")
    assert history["change_percent"] == 37.5
    assert history["base_unit_name"] == "л"


async def test_items_without_a_price_never_reach_the_chart(client: AsyncClient, account_id, categories):
    units = await _units(client)
    piece = units["шт"]
    bread = await _product(client, "Хлеб чёрный", unit_id=piece["id"])

    await _receipt(
        client,
        account_id,
        categories,
        [{"product_id": bread["id"], "name": "Хлеб", "quantity": "1", "unit_id": piece["id"], "amount": "45.00"}],
        amount="45.00",
        date="2026-03-01",
    )
    await _receipt(
        client,
        account_id,
        categories,
        [{"product_id": bread["id"], "name": "Хлеб"}],
        amount="45.00",
        date="2026-04-01",
    )

    history = (await client.get(f"/products/{bread['id']}/prices")).json()
    assert len(history["points"]) == 1
    # Рост считать не от чего — точка одна.
    assert history["change_percent"] is None


async def test_excluded_receipts_stay_out_of_the_price_curve(client: AsyncClient, account_id, categories):
    """Отменённая покупка не должна двигать цену: она не состоялась."""
    units = await _units(client)
    piece = units["шт"]
    bread = await _product(client, "Хлеб чёрный", unit_id=piece["id"])

    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "999.00",
            "description": "Ошибка",
            "date": "2026-03-01",
            "category_id": categories["Groceries"]["id"],
            "is_excluded": True,
            "items": [
                {"product_id": bread["id"], "name": "Хлеб", "quantity": "1", "unit_id": piece["id"], "amount": "999.00"}
            ],
        },
    )
    assert resp.status_code == 201, resp.text

    history = (await client.get(f"/products/{bread['id']}/prices")).json()
    assert history["points"] == []


async def test_product_list_shows_how_alive_each_row_is(client: AsyncClient, account_id, categories):
    """Список товаров без этого — просто список слов: непонятно, что живое,
    а что заведено однажды по ошибке."""
    units = await _units(client)
    piece = units["шт"]
    bread = await _product(client, "Хлеб чёрный", unit_id=piece["id"])
    await _product(client, "Заведён по ошибке")

    await _receipt(
        client,
        account_id,
        categories,
        [{"product_id": bread["id"], "name": "Хлеб", "quantity": "1", "unit_id": piece["id"], "amount": "45.00"}],
        amount="45.00",
        date="2026-03-01",
    )

    products = {row["name"]: row for row in (await client.get("/products")).json()}
    assert products["Хлеб чёрный"]["purchases"] == 1
    assert products["Хлеб чёрный"]["last_bought"] == "2026-03-01"
    assert products["Заведён по ошибке"]["purchases"] == 0
    assert products["Заведён по ошибке"]["last_bought"] is None


async def test_suggestions_find_a_product_by_name_or_barcode(client: AsyncClient):
    await _product(client, "Хлеб чёрный городской", barcode="4600000000017")
    await _product(client, "Молоко 3.2%")

    by_name = (await client.get("/products/suggest?q=хлеб")).json()
    assert [row["name"] for row in by_name] == ["Хлеб чёрный городской"]

    # Отсканировали телефоном — в поле оказался код, а не слово.
    by_code = (await client.get("/products/suggest?q=4600000000017")).json()
    assert [row["name"] for row in by_code] == ["Хлеб чёрный городской"]


async def test_archived_products_are_hidden_but_keep_their_history(client: AsyncClient, account_id, categories):
    units = await _units(client)
    piece = units["шт"]
    bread = await _product(client, "Хлеб чёрный", unit_id=piece["id"])
    await _receipt(
        client,
        account_id,
        categories,
        [{"product_id": bread["id"], "name": "Хлеб", "quantity": "1", "unit_id": piece["id"], "amount": "45.00"}],
        amount="45.00",
        date="2026-03-01",
    )
    await client.patch(f"/products/{bread['id']}", json={"is_archived": True})

    assert (await client.get("/products")).json() == []
    assert len((await client.get("/products?include_archived=true")).json()) == 1
    # История цен у архивного товара остаётся: покупки были.
    history = (await client.get(f"/products/{bread['id']}/prices")).json()
    assert len(history["points"]) == 1


async def test_deleting_a_product_keeps_the_receipt_line(client: AsyncClient, account_id, categories):
    """Покупка была, и стирать её вместе со строкой справочника нельзя."""
    bread = await _product(client, "Хлеб чёрный")
    receipt = await _receipt(
        client,
        account_id,
        categories,
        [{"product_id": bread["id"], "name": "Хлеб городской", "price": "45.00", "quantity": "1"}],
        amount="45.00",
        date="2026-03-01",
    )

    assert (await client.delete(f"/products/{bread['id']}")).status_code == 204

    listing = (await client.get("/transactions")).json()
    row = next(item for item in listing["items"] if item["id"] == receipt["id"])
    assert row["items"][0]["name"] == "Хлеб городской"
    assert row["items"][0]["product_id"] is None


async def test_an_unknown_product_on_an_item_is_rejected(client: AsyncClient, account_id, categories):
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "45.00",
            "description": "Магазин",
            "date": "2026-03-01",
            "category_id": categories["Groceries"]["id"],
            "items": [{"product_id": 99999, "name": "Хлеб"}],
        },
    )
    assert resp.status_code == 400
