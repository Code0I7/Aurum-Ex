"""Long-range reports: the category ranking (which categories cost the
most over an arbitrary period) and the single-category spending detail —
both split-aware via services/category_rollup.py, same as the Dashboard
breakdown (see test_dashboard.py).
"""
from decimal import Decimal

from httpx import AsyncClient

from tests.helpers import money, txn_payload as _txn


async def test_ranking_rolls_up_a_split_into_one_item_with_children(client: AsyncClient, account_id, categories):
    groceries = categories["Groceries"]["id"]
    sweets = (
        await client.post("/categories", json={"name": "Sweets", "kind": "expense", "color": "#7a869a", "parent_id": groceries})
    ).json()["id"]
    await client.post(
        "/transactions",
        json=_txn(
            account_id,
            amount="100.00",
            category_id=None,
            date="2026-08-01",
            splits=[
                {"category_id": groceries, "amount": "70.00"},
                {"category_id": sweets, "amount": "30.00"},
            ],
        ),
    )

    resp = await client.get("/reports/category-ranking", params={"kind": "expense"})
    items = {item["name"]: item for item in resp.json()["items"]}

    assert "Sweets" not in items
    assert money(items["Groceries"]["amount"]) == Decimal("100.00")
    children = {child["name"]: child for child in items["Groceries"]["children"]}
    assert money(children["Groceries"]["amount"]) == Decimal("70.00")
    assert money(children["Sweets"]["amount"]) == Decimal("30.00")


async def test_ranking_item_with_a_single_source_has_no_children(client: AsyncClient, account_id, categories):
    groceries = categories["Groceries"]["id"]
    await client.post("/transactions", json=_txn(account_id, amount="50.00", category_id=groceries, date="2026-08-01"))

    resp = await client.get("/reports/category-ranking", params={"kind": "expense"})
    items = {item["name"]: item for item in resp.json()["items"]}

    assert items["Groceries"]["children"] == []


async def test_category_spending_report_counts_a_subcategorys_split_share(client: AsyncClient, account_id, categories):
    """A top-level category's own report folds in both its plain
    transactions and any split lines landing on it or its subcategories."""
    groceries = categories["Groceries"]["id"]
    sweets = (
        await client.post("/categories", json={"name": "Sweets", "kind": "expense", "color": "#7a869a", "parent_id": groceries})
    ).json()["id"]
    await client.post(
        "/transactions",
        json=_txn(
            account_id,
            amount="100.00",
            category_id=None,
            date="2026-08-01",
            splits=[
                {"category_id": groceries, "amount": "70.00"},
                {"category_id": sweets, "amount": "30.00"},
            ],
        ),
    )

    parent_report = (await client.get("/reports/category-spending", params={"category_id": groceries})).json()
    assert money(parent_report["total_amount"]) == Decimal("100.00")
    assert parent_report["transaction_count"] == 1

    child_report = (await client.get("/reports/category-spending", params={"category_id": sweets})).json()
    assert money(child_report["total_amount"]) == Decimal("30.00")
