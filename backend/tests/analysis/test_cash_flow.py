"""Cash flow: month-by-month income vs. expense across an explicit date
range, or the full transaction history when no range is given.
"""
from decimal import Decimal

from httpx import AsyncClient

from tests.helpers import money, txn_payload


async def test_explicit_range_excludes_transactions_outside_it(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    salary_id = categories["Salary"]["id"]
    await client.post(
        "/transactions", json=txn_payload(account_id, amount="1000.00", type="income", category_id=salary_id, date="2022-05-01")
    )
    await client.post(
        "/transactions", json=txn_payload(account_id, amount="9999.00", type="income", category_id=salary_id, date="2021-01-01")
    )
    await client.post(
        "/transactions", json=txn_payload(account_id, amount="9999.00", type="income", category_id=salary_id, date="2023-01-01")
    )

    resp = await client.get("/cash-flow", params={"start_date": "2022-01-01", "end_date": "2022-12-31"})
    body = resp.json()
    assert money(body["total_income"]) == Decimal("1000.00")
    assert len(body["points"]) == 12  # every month of 2022, including zero months
    assert body["start_date"] == "2022-01-01"
    assert body["end_date"] == "2022-12-31"


async def test_transfers_are_excluded_from_totals(client: AsyncClient, account_id):
    other = await client.post("/accounts", json={"name": "Savings", "kind": "savings", "currency": "USD"})
    other_id = other.json()["id"]
    await client.post(
        "/transactions",
        json=txn_payload(account_id, type="transfer", amount="500.00", transfer_account_id=other_id, date="2022-03-01"),
    )

    resp = await client.get("/cash-flow", params={"start_date": "2022-01-01", "end_date": "2022-12-31"})
    body = resp.json()
    assert money(body["total_income"]) == 0
    assert money(body["total_expense"]) == 0


async def test_no_range_falls_back_to_earliest_and_latest_transaction_dates(
    client: AsyncClient, account_id, categories
):
    category_id = categories["Groceries"]["id"]
    await client.post("/transactions", json=txn_payload(account_id, category_id=category_id, date="2021-06-15"))
    await client.post("/transactions", json=txn_payload(account_id, category_id=category_id, date="2024-02-10"))

    resp = await client.get("/cash-flow")
    body = resp.json()
    assert body["start_date"] == "2021-06-15"
    assert body["end_date"] == "2024-02-10"


async def test_no_transactions_returns_empty_points_and_null_bounds(client: AsyncClient):
    resp = await client.get("/cash-flow")
    body = resp.json()
    assert body["points"] == []
    assert body["start_date"] is None
    assert body["end_date"] is None
    assert money(body["total_net"]) == 0


async def test_monthly_points_split_income_and_expense_correctly(client: AsyncClient, account_id, categories):
    category_id = categories["Groceries"]["id"]
    salary_id = categories["Salary"]["id"]
    await client.post(
        "/transactions", json=txn_payload(account_id, type="income", amount="2000.00", category_id=salary_id, date="2022-04-01")
    )
    await client.post(
        "/transactions", json=txn_payload(account_id, type="expense", amount="300.00", category_id=category_id, date="2022-04-15")
    )

    resp = await client.get("/cash-flow", params={"start_date": "2022-04-01", "end_date": "2022-04-30"})
    point = resp.json()["points"][0]
    assert point["year"] == 2022
    assert point["month"] == 4
    assert money(point["income"]) == Decimal("2000.00")
    assert money(point["expense"]) == Decimal("300.00")
    assert money(point["net"]) == Decimal("1700.00")


# --- Начальные остатки ---


async def test_opening_balance_counts_as_earned(client: AsyncClient, categories):
    """Деньги, лежавшие на счёте до первой записи, тоже были заработаны —
    просто раньше, чем начался учёт. Без них сальдо не сходится с остатком
    на счетах."""
    account = (
        await client.post(
            "/accounts",
            json={
                "name": "Карта",
                "kind": "checking",
                "currency": "RUB",
                "opening_balance": "5210.40",
                "opening_date": "2026-01-15",
            },
        )
    ).json()
    await client.post(
        "/transactions",
        json={
            "account_id": account["id"],
            "type": "expense",
            "amount": "1000.00",
            "description": "Продукты",
            "date": "2026-02-03",
            "category_id": categories["Groceries"]["id"],
        },
    )

    data = (await client.get("/cash-flow")).json()
    january = next(p for p in data["points"] if p["year"] == 2026 and p["month"] == 1)
    assert Decimal(january["income"]) == Decimal("5210.40")
    # Выделен отдельно, чтобы всплеск в месяце открытия счёта был объясним.
    assert Decimal(january["opening"]) == Decimal("5210.40")

    # Сальдо за весь период совпадает с остатком на счёте — ради этого всё и
    # затевалось: 5210,40 начального остатка минус тысяча расхода.
    assert Decimal(data["total_net"]) == Decimal("4210.40")
    assert Decimal(data["total_opening"]) == Decimal("5210.40")

    accounts = (await client.get("/accounts")).json()
    balance = next(a["balance"] for a in accounts if a["id"] == account["id"])
    assert Decimal(balance) == Decimal(data["total_net"])


async def test_negative_opening_balance_is_an_expense_not_negative_income(client: AsyncClient):
    """Счёт, открытый с долгом, — это не отрицательный доход."""
    await client.post(
        "/accounts",
        json={
            "name": "Кредитка",
            "kind": "credit_card",
            "currency": "RUB",
            "opening_balance": "-12000.00",
            "opening_date": "2026-03-01",
        },
    )

    data = (await client.get("/cash-flow")).json()
    march = next(p for p in data["points"] if p["year"] == 2026 and p["month"] == 3)
    assert Decimal(march["income"]) == Decimal("0")
    assert Decimal(march["expense"]) == Decimal("12000.00")
    assert Decimal(march["opening"]) == Decimal("-12000.00")


async def test_opening_outside_the_selected_period_is_not_shown(client: AsyncClient, categories):
    """При фильтре «2026 год» остаток 2025-го показывать неоткуда."""
    account = (
        await client.post(
            "/accounts",
            json={
                "name": "Старая карта",
                "kind": "checking",
                "currency": "RUB",
                "opening_balance": "5000.00",
                "opening_date": "2025-06-01",
            },
        )
    ).json()
    await client.post(
        "/transactions",
        json={
            "account_id": account["id"],
            "type": "expense",
            "amount": "300.00",
            "description": "Продукты",
            "date": "2026-04-10",
            "category_id": categories["Groceries"]["id"],
        },
    )

    data = (await client.get("/cash-flow?start_date=2026-01-01&end_date=2026-12-31")).json()
    assert Decimal(data["total_opening"]) == Decimal("0")
    assert Decimal(data["total_expense"]) == Decimal("300.00")


async def test_opening_widens_the_range_when_it_predates_every_transaction(client: AsyncClient, categories):
    """Счёт открыт раньше первой записи — период начинается с него, иначе
    деньги, с которых всё началось, просто исчезли бы."""
    account = (
        await client.post(
            "/accounts",
            json={
                "name": "Карта",
                "kind": "checking",
                "currency": "RUB",
                "opening_balance": "1000.00",
                "opening_date": "2026-01-10",
            },
        )
    ).json()
    await client.post(
        "/transactions",
        json={
            "account_id": account["id"],
            "type": "expense",
            "amount": "100.00",
            "description": "Продукты",
            "date": "2026-05-01",
            "category_id": categories["Groceries"]["id"],
        },
    )

    data = (await client.get("/cash-flow")).json()
    assert data["points"][0]["month"] == 1
    assert Decimal(data["points"][0]["opening"]) == Decimal("1000.00")
