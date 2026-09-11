"""Budgets: category-kind restriction, one-budget-per-category, and the
spent/remaining/over-budget math behind the Budget page's progress bars.
"""
from decimal import Decimal

from httpx import AsyncClient

from tests.helpers import money, txn_payload


async def test_budget_rejects_income_category(client: AsyncClient, categories):
    resp = await client.post(
        "/budgets", json={"category_id": categories["Salary"]["id"], "monthly_limit": "500.00"}
    )
    assert resp.status_code == 400


async def test_budget_rejects_duplicate_category(client: AsyncClient, categories):
    category_id = categories["Groceries"]["id"]
    first = await client.post("/budgets", json={"category_id": category_id, "monthly_limit": "300.00"})
    assert first.status_code == 201

    second = await client.post("/budgets", json={"category_id": category_id, "monthly_limit": "400.00"})
    assert second.status_code == 400


async def test_status_reports_spent_remaining_and_over_budget(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    await client.post("/budgets", json={"category_id": category_id, "monthly_limit": "100.00"})

    for amount in ["60.00", "60.00"]:  # 120.00 total, over a 100.00 limit
        await client.post(
            "/transactions",
            json=txn_payload(account_id, amount=amount, category_id=category_id, date="2026-08-10"),
        )

    resp = await client.get("/budgets/status", params={"year": 2026, "month": 8})
    item = resp.json()["items"][0]
    assert money(item["spent"]) == Decimal("120.00")
    assert money(item["remaining"]) == Decimal("-20.00")
    assert item["percent"] == 120.0
    assert item["is_over_budget"] is True


async def test_status_only_counts_the_selected_month(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    await client.post("/budgets", json={"category_id": category_id, "monthly_limit": "100.00"})
    await client.post(
        "/transactions", json=txn_payload(account_id, amount="90.00", category_id=category_id, date="2026-07-15")
    )

    resp = await client.get("/budgets/status", params={"year": 2026, "month": 8})
    item = resp.json()["items"][0]
    assert money(item["spent"]) == 0
    assert item["is_over_budget"] is False


async def test_status_is_empty_list_when_no_budgets_exist(client: AsyncClient):
    resp = await client.get("/budgets/status", params={"year": 2026, "month": 8})
    assert resp.json()["items"] == []


async def test_update_budget_changes_the_limit(client: AsyncClient, categories):
    category_id = categories["Groceries"]["id"]
    created = await client.post("/budgets", json={"category_id": category_id, "monthly_limit": "100.00"})
    budget_id = created.json()["id"]

    resp = await client.patch(f"/budgets/{budget_id}", json={"monthly_limit": "250.00"})
    assert resp.status_code == 200
    assert money(resp.json()["monthly_limit"]) == Decimal("250.00")


async def test_delete_budget_removes_it_from_status(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    created = await client.post("/budgets", json={"category_id": category_id, "monthly_limit": "100.00"})
    budget_id = created.json()["id"]

    delete_resp = await client.delete(f"/budgets/{budget_id}")
    assert delete_resp.status_code == 204

    status = await client.get("/budgets/status", params={"year": 2026, "month": 8})
    assert status.json()["items"] == []


async def _subcategory(client: AsyncClient, parent_id: int, name: str = "Rent") -> int:
    resp = await client.post(
        "/categories",
        json={"name": name, "kind": "expense", "color": "#7a869a", "parent_id": parent_id},
    )
    return resp.json()["id"]


async def test_budget_on_a_parent_category_counts_spending_in_its_subcategories(
    client: AsyncClient, account_id, categories
):
    """The Dashboard breakdown and the category report both roll a
    subcategory's spending up into its parent (coalesce(parent_id, id)). A
    budget set on the parent has to agree with them, or the same month reads
    as 900 spent on one screen and 0 on the other."""
    parent_id = categories["Housing & Utilities"]["id"]
    child_id = await _subcategory(client, parent_id)
    await client.post("/budgets", json={"category_id": parent_id, "monthly_limit": "1000.00"})
    await client.post(
        "/transactions", json=txn_payload(account_id, category_id=child_id, amount="900.00", date="2026-03-10")
    )

    status = (await client.get("/budgets/status?year=2026&month=3")).json()["items"][0]
    dashboard = (await client.get("/dashboard/summary?year=2026&month=3")).json()

    assert money(status["spent"]) == money("900.00")
    assert money(status["remaining"]) == money("100.00")
    # The two screens must show the same number for the same category.
    parent_slice = next(s for s in dashboard["spending_by_category"] if s["category_id"] == parent_id)
    assert money(parent_slice["amount"]) == money(status["spent"])


async def test_a_subcategory_keeps_its_own_budget_separate(client: AsyncClient, account_id, categories):
    """Rolling children into a parent's budget must not swallow a budget set
    on the child itself — both bars track the same spending, each against its
    own limit."""
    parent_id = categories["Housing & Utilities"]["id"]
    child_id = await _subcategory(client, parent_id)
    await client.post("/budgets", json={"category_id": parent_id, "monthly_limit": "1000.00"})
    await client.post("/budgets", json={"category_id": child_id, "monthly_limit": "800.00"})
    await client.post(
        "/transactions", json=txn_payload(account_id, category_id=child_id, amount="900.00", date="2026-03-10")
    )

    items = {item["category_id"]: item for item in (await client.get("/budgets/status?year=2026&month=3")).json()["items"]}

    assert money(items[child_id]["spent"]) == money("900.00")
    assert items[child_id]["is_over_budget"] is True
    assert money(items[parent_id]["spent"]) == money("900.00")
    assert items[parent_id]["is_over_budget"] is False


async def test_budget_status_counts_a_split_transactions_share(client: AsyncClient, account_id, categories):
    """A receipt split between Groceries and one of its own subcategories
    (Sweets) must count each line toward the right budget: the full 100.00
    rolls up into the Groceries budget, but only the 30.00 Sweets line
    counts toward a budget set on Sweets itself."""
    groceries = categories["Groceries"]["id"]
    sweets_resp = await client.post(
        "/categories", json={"name": "Sweets", "kind": "expense", "color": "#7a869a", "parent_id": groceries}
    )
    sweets = sweets_resp.json()["id"]
    await client.post("/budgets", json={"category_id": groceries, "monthly_limit": "100.00"})
    await client.post("/budgets", json={"category_id": sweets, "monthly_limit": "50.00"})
    await client.post(
        "/transactions",
        json=txn_payload(
            account_id,
            amount="100.00",
            category_id=None,
            date="2026-08-10",
            splits=[
                {"category_id": groceries, "amount": "70.00"},
                {"category_id": sweets, "amount": "30.00"},
            ],
        ),
    )

    resp = await client.get("/budgets/status", params={"year": 2026, "month": 8})
    items = {item["category_id"]: item for item in resp.json()["items"]}
    assert money(items[groceries]["spent"]) == Decimal("100.00")
    assert money(items[sweets]["spent"]) == Decimal("30.00")


async def _plan(client: AsyncClient, category_id: int, amount: str, kind: str = "monthly", **extra) -> dict:
    payload = {
        "category_id": category_id,
        "kind": kind,
        "periods": [{"amount": amount, "valid_from": extra.pop("valid_from", "2026-01-01")}],
        **extra,
    }
    resp = await client.post("/plans", json=payload)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def test_a_planned_category_gets_a_budget_line_without_a_budget(
    client: AsyncClient, account_id, categories
):
    """Бюджет и планирование описывали одно и то же разными словами, и
    советы требовали завести бюджет там, где план уже был. Категория с
    планом теперь получает строку бюджета сама."""
    groceries = categories["Groceries"]["id"]
    await _plan(client, groceries, "5000.00")

    body = (await client.get("/budgets/status", params={"year": 2026, "month": 3})).json()
    line = next(item for item in body["items"] if item["category_id"] == groceries)
    assert line["source"] == "plan"
    assert line["budget_id"] is None
    assert Decimal(line["monthly_limit"]) == Decimal("5000.00")


async def test_an_own_budget_wins_over_the_plan(client: AsyncClient, categories):
    """Правило старшинства: свой бюджет вытесняет плановую строку, а не
    спорит с ней. Поэтому и предупреждать не о чем."""
    groceries = categories["Groceries"]["id"]
    await _plan(client, groceries, "5000.00")
    await client.post("/budgets", json={"category_id": groceries, "monthly_limit": "4000.00"})

    body = (await client.get("/budgets/status", params={"year": 2026, "month": 3})).json()
    lines = [item for item in body["items"] if item["category_id"] == groceries]
    assert len(lines) == 1
    assert lines[0]["source"] == "budget"
    assert Decimal(lines[0]["monthly_limit"]) == Decimal("4000.00")


async def test_a_plan_line_changes_from_month_to_month(client: AsyncClient, categories):
    """Плановая строка точнее обычного бюджета: у того один потолок на все
    месяцы, а разовая покупка стоит только в своём."""
    shopping = categories["Shopping"]["id"]
    await _plan(client, shopping, "60000.00", kind="one_off", valid_from="2026-05-01")

    may = (await client.get("/budgets/status", params={"year": 2026, "month": 5})).json()
    assert any(item["category_id"] == shopping for item in may["items"])
    june = (await client.get("/budgets/status", params={"year": 2026, "month": 6})).json()
    assert not any(item["category_id"] == shopping for item in june["items"])


async def test_income_plans_never_become_budget_lines(client: AsyncClient, categories):
    """План на зарплату — ожидание дохода, а не потолок траты. Полоса
    «истрачено 96%» для него означала бы обратное происходящему."""
    salary = categories["Salary"]["id"]
    await _plan(client, salary, "80000.00")

    body = (await client.get("/budgets/status", params={"year": 2026, "month": 3})).json()
    assert not any(item["category_id"] == salary for item in body["items"])


async def test_advice_stops_asking_for_a_budget_a_plan_already_covers(
    client: AsyncClient, account_id, categories
):
    """Совет смотрел только в таблицу бюджетов и просил завести вторую
    запись про ту же цифру."""
    groceries = categories["Groceries"]["id"]
    await _plan(client, groceries, "5000.00")
    await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "4000.00",
            "description": "Продукты",
            "date": "2026-03-10",
            "category_id": groceries,
        },
    )

    advice = (await client.get("/advice", params={"year": 2026, "month": 3})).json()
    unbudgeted = [item for item in advice["items"] if item["key"] == "unbudgeted_top_category"]
    assert all(item["params"]["category"] != "Groceries" for item in unbudgeted)
