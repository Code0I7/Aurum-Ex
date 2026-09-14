"""Итоги складываются в валюте установки.

Доход, расходы, разбивка по категориям, бюджет, движение денежных средств —
всё это складывает операции разных счетов, а значит и разных валют. Раньше
все эти итоги брали сумму операции как есть: пока счета рублёвые, ошибки не
видно, но трата на 10 $ входила в расходы как 10 ₽.

Остаток счёта здесь ни при чём — он состояние и считается в валюте самого
счёта (см. test_net_worth_currency.py).
"""
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.currency import ExchangeRate


def money(value: str) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


async def _account(client: AsyncClient, name: str, currency: str) -> int:
    resp = await client.post("/accounts", json={"name": name, "kind": "checking", "currency": currency})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _spend(client: AsyncClient, account_id: int, amount: str, on: str, **extra) -> dict:
    resp = await client.post(
        "/transactions",
        json={"account_id": account_id, "type": "expense", "amount": amount, "date": on, **extra},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _setup(client: AsyncClient, session: AsyncSession, categories) -> dict:
    """100 ₽ и две траты по 10 $ по курсу 80: одна целиком в продукты,
    вторая разделена 6 $ / 4 $ между продуктами и сладким."""
    session.add(ExchangeRate(code="USD", rate_date=date(2026, 8, 5), rate=Decimal("80")))
    await session.commit()

    groceries = categories["Groceries"]["id"]
    sweets = (
        await client.post(
            "/categories",
            json={"name": "Sweets", "kind": "expense", "color": "#7a869a", "parent_id": groceries},
        )
    ).json()["id"]

    rouble = await _account(client, "Рублёвая", "RUB")
    dollar = await _account(client, "Долларовая", "USD")
    await _spend(client, rouble, "100.00", "2026-08-05", category_id=groceries)
    await _spend(client, dollar, "10.00", "2026-08-05", category_id=groceries)
    await _spend(
        client,
        dollar,
        "10.00",
        "2026-08-05",
        splits=[
            {"category_id": groceries, "amount": "6.00"},
            {"category_id": sweets, "amount": "4.00"},
        ],
    )
    return {"groceries": groceries, "sweets": sweets, "rouble": rouble, "dollar": dollar}


async def test_dashboard_totals_and_breakdown_are_in_base_currency(
    client: AsyncClient, session: AsyncSession, categories
):
    await _setup(client, session, categories)

    body = (await client.get("/dashboard/summary", params={"year": 2026, "month": 8})).json()

    # 100 + 800 + 800, а не 100 + 10 + 10.
    assert money(body["spent"]) == Decimal("1700.00")
    breakdown = {row["name"]: row for row in body["spending_by_category"]}
    assert money(breakdown["Groceries"]["amount"]) == Decimal("1700.00")
    children = {child["name"]: child for child in breakdown["Groceries"]["children"]}
    # Доля разделённой траты — тем же курсом, что и вся трата: 4 $ × 80.
    assert money(children["Sweets"]["amount"]) == Decimal("320.00")
    # Крупнейшие траты сравниваются в одной валюте: 10 $ больше 100 ₽.
    assert money(body["largest_expenses"][0]["amount"]) == Decimal("800.00")
    assert money(body["largest_expenses"][-1]["amount"]) == Decimal("100.00")


async def test_budget_compares_its_limit_with_base_currency_spend(
    client: AsyncClient, session: AsyncSession, categories
):
    ids = await _setup(client, session, categories)
    resp = await client.post("/budgets", json={"category_id": ids["groceries"], "monthly_limit": "1000"})
    assert resp.status_code == 201, resp.text

    status = (await client.get("/budgets/status", params={"year": 2026, "month": 8})).json()
    line = next(item for item in status["items"] if item["category_id"] == ids["groceries"])

    assert money(line["spent"]) == Decimal("1700.00")
    assert line["is_over_budget"] is True


async def test_cash_flow_and_category_report_are_in_base_currency(
    client: AsyncClient, session: AsyncSession, categories
):
    ids = await _setup(client, session, categories)

    flow = (
        await client.get("/cash-flow", params={"start_date": "2026-08-01", "end_date": "2026-08-31"})
    ).json()
    assert money(flow["total_expense"]) == Decimal("1700.00")

    report = (
        await client.get(
            "/reports/category-spending",
            params={"category_id": ids["groceries"], "start_date": "2026-08-01", "end_date": "2026-08-31"},
        )
    ).json()
    assert money(report["total_amount"]) == Decimal("1700.00")


async def test_category_report_leaves_out_excluded_purchases(
    client: AsyncClient, session: AsyncSession, categories
):
    """Возвращённая покупка выпала из рейтинга категорий и с обзора — и из
    отчёта по одной категории обязана выпасть так же, иначе одна категория
    показывает два разных числа."""
    ids = await _setup(client, session, categories)
    await _spend(client, ids["rouble"], "500.00", "2026-08-06", category_id=ids["groceries"], is_excluded=True)

    report = (
        await client.get(
            "/reports/category-spending",
            params={"category_id": ids["groceries"], "start_date": "2026-08-01", "end_date": "2026-08-31"},
        )
    ).json()
    assert money(report["total_amount"]) == Decimal("1700.00")


async def test_a_purchase_without_a_rate_stays_out_of_every_total(
    client: AsyncClient, session: AsyncSession, categories
):
    """Курса на 1 августа нет — первый известный только с пятого, а более
    поздний курс на более раннюю дату не берётся: трата сохранена, но в
    итоги не входит — ни как 25 ₽, ни как ошибка."""
    ids = await _setup(client, session, categories)
    await _spend(client, ids["dollar"], "25.00", "2026-08-01", category_id=ids["groceries"])

    body = (await client.get("/dashboard/summary", params={"year": 2026, "month": 8})).json()
    assert money(body["spent"]) == Decimal("1700.00")
    flow = (
        await client.get("/cash-flow", params={"start_date": "2026-08-01", "end_date": "2026-08-31"})
    ).json()
    assert money(flow["total_expense"]) == Decimal("1700.00")
