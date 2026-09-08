"""Суммы в дереве категорий."""
from decimal import Decimal

from httpx import AsyncClient


async def test_category_totals_split_own_from_the_whole_branch(client: AsyncClient, account_id, categories):
    """Два числа, а не одно: разница отвечает на вопрос «сколько тут
    неразобранного» — крупный own у ветки означает, что траты сваливают в
    корень, не выбирая подкатегорию."""
    groceries = categories["Groceries"]["id"]
    dairy = (
        await client.post(
            "/categories",
            json={"name": "Молочное", "kind": "expense", "color": "#557799", "parent_id": groceries},
        )
    ).json()
    cheese = (
        await client.post(
            "/categories",
            json={"name": "Сыр", "kind": "expense", "color": "#557799", "parent_id": dairy["id"]},
        )
    ).json()

    for category_id, amount in ((groceries, "100.00"), (dairy["id"], "200.00"), (cheese["id"], "450.00")):
        resp = await client.post(
            "/transactions",
            json={
                "account_id": account_id,
                "type": "expense",
                "amount": amount,
                "description": "Покупка",
                "date": "2026-03-05",
                "category_id": category_id,
            },
        )
        assert resp.status_code == 201, resp.text

    totals = {row["category_id"]: row for row in (await client.get("/categories/totals")).json()}
    assert Decimal(totals[groceries]["own"]) == Decimal("100")
    assert Decimal(totals[groceries]["total"]) == Decimal("750")
    assert Decimal(totals[dairy["id"]]["own"]) == Decimal("200")
    assert Decimal(totals[dairy["id"]]["total"]) == Decimal("650")
    # У листа оба числа совпадают: ветки под ним нет.
    assert Decimal(totals[cheese["id"]]["own"]) == Decimal("450")
    assert Decimal(totals[cheese["id"]]["total"]) == Decimal("450")


async def test_totals_can_be_limited_to_a_period(client: AsyncClient, account_id, categories):
    groceries = categories["Groceries"]["id"]
    for amount, date in (("100.00", "2025-06-01"), ("200.00", "2026-03-05")):
        await client.post(
            "/transactions",
            json={
                "account_id": account_id,
                "type": "expense",
                "amount": amount,
                "description": "Покупка",
                "date": date,
                "category_id": groceries,
            },
        )

    everything = {row["category_id"]: row for row in (await client.get("/categories/totals")).json()}
    assert Decimal(everything[groceries]["total"]) == Decimal("300")

    year = {
        row["category_id"]: row
        for row in (await client.get("/categories/totals?start_date=2026-01-01&end_date=2026-12-31")).json()
    }
    assert Decimal(year[groceries]["total"]) == Decimal("200")


async def test_untouched_categories_report_zero_not_absence(client: AsyncClient, categories):
    """Категория без единой операции остаётся в ответе: ноль — это ответ, а
    отсутствие строки заставило бы интерфейс гадать."""
    totals = {row["category_id"]: row for row in (await client.get("/categories/totals")).json()}
    groceries = categories["Groceries"]["id"]
    assert Decimal(totals[groceries]["total"]) == Decimal("0")
    assert totals[groceries]["transactions"] == 0
