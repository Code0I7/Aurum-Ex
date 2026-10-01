"""Сколько денег ушло на конкретный товар.

Кривая цены отвечает на вопрос «дорожает ли», а эта сводка — на «сколько
мне это стоит»: полтинник за батон незаметен, три тысячи за год на хлеб —
уже разговор.
"""
from datetime import date, timedelta
from decimal import Decimal

from httpx import AsyncClient

from tests.helpers import txn_payload


async def _product(client: AsyncClient, name: str) -> dict:
    resp = await client.post("/products", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _buy(client: AsyncClient, account_id: int, product: dict, amount: str, on: date) -> None:
    resp = await client.post(
        "/transactions",
        json=txn_payload(
            account_id,
            amount=amount,
            description="Покупка",
            date=on.isoformat(),
            items=[{"name": product["name"], "product_id": product["id"], "amount": amount}],
        ),
    )
    assert resp.status_code == 201, resp.text


async def test_spending_sums_every_purchase(client: AsyncClient, account_id):
    bread = await _product(client, "Хлеб бородинский")
    today = date.today()
    await _buy(client, account_id, bread, "45.00", today)
    await _buy(client, account_id, bread, "48.00", today - timedelta(days=30))

    row = next(p for p in (await client.get("/products")).json() if p["id"] == bread["id"])
    assert Decimal(row["spent_total"]) == Decimal("93.00")
    assert row["purchases"] == 2


async def test_year_window_is_rolling_not_calendar(client: AsyncClient, account_id):
    """Календарный год в январе показывал бы траты за две недели и
    выглядел бы падением там, где его нет."""
    bread = await _product(client, "Хлеб")
    today = date.today()
    await _buy(client, account_id, bread, "100.00", today - timedelta(days=10))
    await _buy(client, account_id, bread, "200.00", today - timedelta(days=400))

    row = next(p for p in (await client.get("/products")).json() if p["id"] == bread["id"])
    assert Decimal(row["spent_total"]) == Decimal("300.00")
    # Покупка четырёхсотдневной давности в скользящий год не попадает.
    assert Decimal(row["spent_year"]) == Decimal("100.00")


async def test_product_without_purchases_shows_zero(client: AsyncClient):
    """Заведённый и ни разу не купленный товар — ноль, а не пусто: пустое
    место в колонке читается как поломка."""
    product = await _product(client, "Не покупали")
    row = next(p for p in (await client.get("/products")).json() if p["id"] == product["id"])
    assert Decimal(row["spent_total"]) == Decimal("0")
    assert Decimal(row["spent_year"]) == Decimal("0")
