"""Кривая цены, когда покупали в разных валютах.

Цена — событие: сколько отдали в тот день. События переводятся один раз,
курсом своего дня, и после этого сравнимы между собой. Без перевода покупка
за евро легла бы на рублёвую кривую своим числом, и «сыр подешевел втрое»
означало бы только то, что в тот раз платили не рублями.

Этим цена и отличается от единиц измерения, где линии разводятся по видам:
килограммы с литрами несравнимы в принципе, а валюты сравнимы — на то и
курс.
"""
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.currency import ExchangeRate


async def _product(client: AsyncClient, name: str) -> dict:
    resp = await client.post("/products", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _unit(client: AsyncClient, name: str = "кг") -> dict:
    units = (await client.get("/units")).json()
    return next(unit for unit in units if unit["name"] == name)


async def _buy(
    client: AsyncClient,
    account_id: int,
    product_id: int,
    unit_id: int,
    amount: str,
    quantity: str,
    on: str,
) -> None:
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": amount,
            "description": "Покупка",
            "date": on,
            "items": [
                {
                    "name": "Сыр",
                    "product_id": product_id,
                    "unit_id": unit_id,
                    "amount": amount,
                    "quantity": quantity,
                }
            ],
        },
    )
    assert resp.status_code == 201, resp.text


async def _account(client: AsyncClient, name: str, currency: str) -> dict:
    resp = await client.post(
        "/accounts", json={"name": name, "kind": "checking", "currency": currency}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_a_purchase_in_another_currency_lands_on_the_same_curve(
    client: AsyncClient, session: AsyncSession
):
    """Два килограмма по одной цене — один за рубли, другой за евро по
    курсу того дня. На кривой это одна и та же цена, а не падение втрое."""
    session.add(ExchangeRate(code="EUR", rate_date=date(2026, 3, 6), rate=Decimal("100.0")))
    await session.commit()

    roubles = await _account(client, "Рублёвая", "RUB")
    euros = await _account(client, "Евровая", "EUR")
    product = await _product(client, "Сыр")
    unit = await _unit(client)

    await _buy(client, roubles["id"], product["id"], unit["id"], "1000.00", "1", "2026-03-05")
    await _buy(client, euros["id"], product["id"], unit["id"], "10.00", "1", "2026-03-06")

    history = (await client.get(f"/products/{product['id']}/prices")).json()
    prices = [Decimal(point["price_per_base_unit"]) for point in history["series"][0]["points"]]

    # Десять евро по сто — это та же тысяча, и цена не изменилась.
    assert prices == [Decimal("1000"), Decimal("1000")]


async def test_a_purchase_without_a_rate_stays_off_the_curve(client: AsyncClient):
    """Выдумать курс хуже, чем пропустить точку: неизвестная цена не должна
    выглядеть как известная."""
    euros = await _account(client, "Евровая", "EUR")
    product = await _product(client, "Сыр")
    unit = await _unit(client)

    await _buy(client, euros["id"], product["id"], unit["id"], "10.00", "1", "2026-03-06")

    history = (await client.get(f"/products/{product['id']}/prices")).json()

    assert history["series"] == []
    # И сказано, сколько покупок осталось за кривой.
    assert history["unmeasured"] == 1


async def test_the_product_list_totals_are_converted_too(
    client: AsyncClient, session: AsyncSession
):
    """«Потрачено на товар» складывается из покупок, а сложить их можно
    только приведёнными."""
    session.add(ExchangeRate(code="EUR", rate_date=date(2026, 3, 6), rate=Decimal("100.0")))
    await session.commit()

    roubles = await _account(client, "Рублёвая", "RUB")
    euros = await _account(client, "Евровая", "EUR")
    product = await _product(client, "Сыр")
    unit = await _unit(client)

    await _buy(client, roubles["id"], product["id"], unit["id"], "1000.00", "1", "2026-03-05")
    await _buy(client, euros["id"], product["id"], unit["id"], "10.00", "1", "2026-03-06")

    listed = next(
        row for row in (await client.get("/products")).json() if row["id"] == product["id"]
    )

    # Тысяча рублями плюс десять евро по сто — две тысячи, а не тысяча
    # десять.
    assert Decimal(listed["spent_total"]) == Decimal("2000.00")
