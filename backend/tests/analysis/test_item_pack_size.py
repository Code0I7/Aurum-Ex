"""Один товар, разные меры: упаковки против граммов.

Человек считает товар то упаковками, то весом. Приложение приводило
количество к базовой мере через коэффициент единицы, но рода единицы не
смотрело вовсе — и штуки попадали на одну ось с килограммами. Шоколад,
купленный раз как «90 г за 89 ₽» (989 ₽/кг) и раз как «1 шт за 89 ₽»
(89 ₽/шт), показывал падение цены на 91%, которого не было.

Мостом между мерами служит размер упаковки в позиции чека: «2 шт × 0,9 л» —
это 1,8 л. Лежит он в позиции, а не в товаре, потому что фасовку ужимают: в
товаре одно число задним числом пересчитало бы всю прошлую историю по новому
размеру и спрятало бы ровно то подорожание, ради которого учёт цен и ведут.

Размер необязателен, и это тоже намеренно. Развесной товар, расфасованный в
магазине, каждый раз весит по-своему: раз человек переписал вес с ценника,
другой раз забыл. Забытый вес не придумывается из прошлой покупки — такая
позиция просто остаётся на кривой «за упаковку».
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


async def _receipt(
    client: AsyncClient, account_id: int, categories, items: list[dict], amount: str, date: str
) -> dict:
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


def _by_unit(history: dict) -> dict[str, dict]:
    return {series["base_unit_name"]: series for series in history["series"]}


async def test_a_pack_size_turns_pieces_into_litres(client: AsyncClient, account_id, categories):
    """«2 шт × 0,9 л по 100 ₽ за литр» — это 180 ₽ и 100 ₽ за литр."""
    units = await _units(client)
    milk = await _product(client, "Молоко 3.2%")

    receipt = await _receipt(
        client,
        account_id,
        categories,
        [
            {
                "product_id": milk["id"],
                "name": "Молоко",
                "quantity": "2",
                "unit_id": units["шт"]["id"],
                "pack_size": "0.9",
                "pack_unit_id": units["л"]["id"],
                "price": "100.00",
            }
        ],
        amount="180.00",
        date="2026-03-01",
    )
    assert Decimal(receipt["items"][0]["amount"]) == Decimal("180.00")

    history = (await client.get(f"/products/{milk['id']}/prices")).json()
    series = _by_unit(history)["л"]
    assert Decimal(series["points"][0]["price_per_base_unit"]).quantize(Decimal("0.01")) == Decimal(
        "100.00"
    )


async def test_a_pack_size_makes_pieces_comparable_with_volume(
    client: AsyncClient, account_id, categories
):
    """Ради этого размер и заводится: обе покупки на одной кривой."""
    units = await _units(client)
    milk = await _product(client, "Молоко 3.2%")

    # Первый раз записано штукой с размером, второй — сразу в миллилитрах.
    await _receipt(
        client,
        account_id,
        categories,
        [
            {
                "product_id": milk["id"],
                "name": "Молоко",
                "quantity": "1",
                "unit_id": units["шт"]["id"],
                "pack_size": "900",
                "pack_unit_id": units["мл"]["id"],
                "amount": "90.00",
            }
        ],
        amount="90.00",
        date="2026-03-01",
    )
    await _receipt(
        client,
        account_id,
        categories,
        [
            {
                "product_id": milk["id"],
                "name": "Молоко",
                "quantity": "900",
                "unit_id": units["мл"]["id"],
                "amount": "99.00",
            }
        ],
        amount="99.00",
        date="2026-04-01",
    )

    history = (await client.get(f"/products/{milk['id']}/prices")).json()
    assert len(history["series"]) == 1, history["series"]
    series = history["series"][0]
    assert series["base_unit_name"] == "л"
    assert [
        Decimal(point["price_per_base_unit"]).quantize(Decimal("0.01")) for point in series["points"]
    ] == [Decimal("100.00"), Decimal("110.00")]
    assert series["change_percent"] == 10.0


async def test_pieces_and_grams_never_share_a_curve(client: AsyncClient, account_id, categories):
    """Без размера упаковки это разные величины, и общая кривая врала бы.

    Тот самый случай: 989 ₽ за килограмм и 89 ₽ за штуку на одной оси
    читались как обвал цены на 91%.
    """
    units = await _units(client)
    chocolate = await _product(client, "Шоколад Горький")

    await _receipt(
        client,
        account_id,
        categories,
        [
            {
                "product_id": chocolate["id"],
                "name": "Шоколад",
                "quantity": "90",
                "unit_id": units["г"]["id"],
                "amount": "89.00",
            }
        ],
        amount="89.00",
        date="2026-03-01",
    )
    await _receipt(
        client,
        account_id,
        categories,
        [
            {
                "product_id": chocolate["id"],
                "name": "Шоколад",
                "quantity": "1",
                "unit_id": units["шт"]["id"],
                "amount": "89.00",
            }
        ],
        amount="89.00",
        date="2026-04-01",
    )

    history = (await client.get(f"/products/{chocolate['id']}/prices")).json()
    by_unit = _by_unit(history)
    assert set(by_unit) == {"кг", "шт"}
    assert Decimal(by_unit["кг"]["last_price"]).quantize(Decimal("0.01")) == Decimal("988.89")
    assert Decimal(by_unit["шт"]["last_price"]).quantize(Decimal("0.01")) == Decimal("89.00")
    # Ни у одной кривой нет падения: падения и не было.
    assert by_unit["кг"]["change_percent"] is None
    assert by_unit["шт"]["change_percent"] is None


async def test_a_forgotten_weight_is_not_invented(client: AsyncClient, account_id, categories):
    """Развесной товар, расфасованный в магазине: вес каждый раз свой.

    Раз человек переписал его с ценника, другой раз забыл. Забытый вес не
    берётся из прошлой покупки — иначе придуманное число село бы на кривую
    «за килограмм» и выглядело бы записанным.
    """
    units = await _units(client)
    cheese = await _product(client, "Сыр Гауда")

    await _receipt(
        client,
        account_id,
        categories,
        [
            {
                "product_id": cheese["id"],
                "name": "Сыр",
                "quantity": "1",
                "unit_id": units["шт"]["id"],
                "pack_size": "340",
                "pack_unit_id": units["г"]["id"],
                "amount": "289.00",
            }
        ],
        amount="289.00",
        date="2026-03-01",
    )
    await _receipt(
        client,
        account_id,
        categories,
        [
            {
                "product_id": cheese["id"],
                "name": "Сыр",
                "quantity": "1",
                "unit_id": units["шт"]["id"],
                "amount": "310.00",
            }
        ],
        amount="310.00",
        date="2026-04-01",
    )

    history = (await client.get(f"/products/{cheese['id']}/prices")).json()
    by_unit = _by_unit(history)
    # Покупка с весом — на весовой кривой, без веса — на упаковочной.
    assert set(by_unit) == {"кг", "шт"}
    assert Decimal(by_unit["кг"]["last_price"]).quantize(Decimal("0.01")) == Decimal("850.00")
    assert Decimal(by_unit["шт"]["last_price"]).quantize(Decimal("0.01")) == Decimal("310.00")

    # И размер не подставляется в следующую позицию: по одной покупке
    # постоянную фасовку от развесной не отличить.
    product = next(row for row in (await client.get("/products")).json() if row["id"] == cheese["id"])
    assert product["last_pack_size"] is None


async def test_a_settled_pack_size_gets_substituted(client: AsyncClient, account_id, categories):
    """Молоко в литровых пакетах: два раза подряд один размер — значит,
    фасовка постоянная, и вводить её в третий раз незачем."""
    units = await _units(client)
    milk = await _product(client, "Молоко 3.2%")

    for date in ("2026-03-01", "2026-04-01"):
        await _receipt(
            client,
            account_id,
            categories,
            [
                {
                    "product_id": milk["id"],
                    "name": "Молоко",
                    "quantity": "1",
                    "unit_id": units["шт"]["id"],
                    "pack_size": "0.9",
                    "pack_unit_id": units["л"]["id"],
                    "amount": "90.00",
                }
            ],
            amount="90.00",
            date=date,
        )

    product = next(row for row in (await client.get("/products")).json() if row["id"] == milk["id"])
    assert Decimal(product["last_pack_size"]) == Decimal("0.9000")
    assert product["last_pack_unit_id"] == units["л"]["id"]


async def test_the_last_price_is_labelled_by_what_was_measured(
    client: AsyncClient, account_id, categories
):
    """Товар записан в граммах, куплен однажды штукой — и «89» подписывалось
    как «₽ / кг», то есть ценник за упаковку назывался ценой за килограмм."""
    units = await _units(client)
    chocolate = await _product(client, "Шоколад Горький", unit_id=units["г"]["id"])

    await _receipt(
        client,
        account_id,
        categories,
        [
            {
                "product_id": chocolate["id"],
                "name": "Шоколад",
                "quantity": "1",
                "unit_id": units["шт"]["id"],
                "amount": "89.00",
            }
        ],
        amount="89.00",
        date="2026-03-01",
    )

    product = next(
        row for row in (await client.get("/products")).json() if row["id"] == chocolate["id"]
    )
    assert product["base_unit_name"] == "шт"
    assert Decimal(product["last_price_per_base_unit"]).quantize(Decimal("0.01")) == Decimal("89.00")


async def test_purchases_without_a_price_are_counted_separately(
    client: AsyncClient, account_id, categories
):
    """«Купили хлеб и молоко» помнят без цен. В кривую такие не идут, но
    молчать о них нельзя: иначе непонятно, почему покупок две, а точка одна."""
    bread = await _product(client, "Хлеб чёрный")

    await _receipt(
        client,
        account_id,
        categories,
        [{"product_id": bread["id"], "name": "Хлеб", "quantity": "1", "amount": "45.00"}],
        amount="45.00",
        date="2026-03-01",
    )
    await _receipt(
        client,
        account_id,
        categories,
        [{"product_id": bread["id"], "name": "Хлеб"}],
        amount="50.00",
        date="2026-04-01",
    )

    history = (await client.get(f"/products/{bread['id']}/prices")).json()
    assert history["unmeasured"] == 1
    assert sum(len(series["points"]) for series in history["series"]) == 1
