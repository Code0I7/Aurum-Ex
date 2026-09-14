"""Долг по кредитке вычитается из капитала и из быстрых денег.

Отбор счетов для денежного ряда шёл по виду, и кредитной карты в нём не
было вовсе: капитал показывал сумму положительных счетов, а долг по картам
не вычитался никогда. 127 тысяч там, где на самом деле 72 — хотя в
описании «быстрых денег» с самого начала было «за вычетом долга по картам».
"""
from decimal import Decimal

from httpx import AsyncClient


async def _account(client: AsyncClient, name: str, kind: str, opening: str = "0") -> dict:
    resp = await client.post(
        "/accounts", json={"name": name, "kind": kind, "opening_balance": opening}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _spend(client: AsyncClient, account_id: int, amount: str) -> None:
    resp = await client.post(
        "/transactions",
        json={"account_id": account_id, "type": "expense", "amount": amount, "date": "2026-03-05"},
    )
    assert resp.status_code == 201, resp.text


async def _summary(client: AsyncClient) -> dict:
    resp = await client.get("/net-worth/summary?range=all")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_credit_card_debt_is_subtracted_from_capital(client: AsyncClient):
    """Ради этого всё: 1000 на карте и 400 долга по кредитке — это 600."""
    await _account(client, "Дебетовая", "checking", "1000")
    credit = await _account(client, "Кредитка", "credit_card")
    await _spend(client, credit["id"], "400.00")

    summary = await _summary(client)

    assert Decimal(summary["current"]) == Decimal("600.00")
    assert Decimal(summary["liquid"]) == Decimal("600.00")
    # И сколько должно — отдельным числом, чтобы итог не был загадкой.
    assert Decimal(summary["liabilities"]) == Decimal("400.00")


async def test_the_breakdown_describes_what_there_is_not_what_is_owed(client: AsyncClient):
    """Разбивка отвечает на «из чего состоит имущество». Долг в ней не
    строка, и доли складываются в сто, сколько бы ни было должно."""
    await _account(client, "Дебетовая", "checking", "1000")
    credit = await _account(client, "Кредитка", "credit_card")
    await _spend(client, credit["id"], "400.00")

    breakdown = (await _summary(client))["breakdown"]

    bank = next(row for row in breakdown if row["key"] == "bank")
    assert Decimal(bank["amount"]) == Decimal("1000.00")
    assert round(sum(row["percent"] for row in breakdown)) == 100


async def test_a_loan_counts_as_debt_too(client: AsyncClient):
    """Рассрочка без пластика — тот же долг, что и по карте."""
    await _account(client, "Дебетовая", "checking", "5000")
    loan = await _account(client, "Рассрочка", "loan")
    await _spend(client, loan["id"], "2000.00")

    summary = await _summary(client)

    assert Decimal(summary["current"]) == Decimal("3000.00")
    assert Decimal(summary["liabilities"]) == Decimal("2000.00")


async def test_a_card_with_no_debt_changes_nothing(client: AsyncClient):
    debit = await _account(client, "Дебетовая", "checking", "1000")
    await _account(client, "Кредитка", "credit_card")
    # Ряд капитала строится по дням с операциями; без единой операции он
    # пуст, и сравнивать было бы не с чем.
    await _spend(client, debit["id"], "100.00")

    summary = await _summary(client)

    assert Decimal(summary["current"]) == Decimal("900.00")
    assert Decimal(summary["liabilities"]) == Decimal("0")
