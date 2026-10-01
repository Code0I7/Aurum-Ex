"""Условия по кредитам: ставка, лимит, оценка процентов.

Долг сам по себе уже описан счётом — отрицательным балансом. Здесь
проверяется то, чего в таблице не было: во сколько этот долг обходится.
"""
from decimal import Decimal

from httpx import AsyncClient


async def _credit_account(client: AsyncClient, name: str = "Банк Кр") -> int:
    resp = await client.post(
        "/accounts",
        json={"name": name, "kind": "credit_card", "currency": "RUB"},
    )
    assert resp.status_code == 201, resp.text
    account = resp.json()
    # Природа выводится из вида счёта: кредитная карта — обязательство, и
    # указывать это отдельно пользователь не должен.
    assert account["nature"] == "liability"
    return account["id"]


async def _spend(client: AsyncClient, account_id: int, amount: str, categories) -> None:
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": amount,
            "description": "Покупка в рассрочку",
            "date": "2026-09-01",
            "category_id": categories["Groceries"]["id"],
        },
    )
    assert resp.status_code == 201, resp.text


async def test_terms_cannot_be_attached_to_a_debit_account(client: AsyncClient, account_id):
    """Ставка на дебетовой карте означала бы, что владелец неверно понял,
    что такое счёт. Молча принять такую запись — оставить ошибку навсегда."""
    resp = await client.put(
        f"/accounts/{account_id}/credit-terms", json={"annual_rate_percent": "24.9"}
    )
    assert resp.status_code == 400


async def test_terms_are_created_and_updated_by_one_call(client: AsyncClient):
    credit_id = await _credit_account(client)

    # Условий ещё нет — это отдельное состояние, а не нулевая ставка.
    assert (await client.get(f"/accounts/{credit_id}/credit-terms")).status_code == 404

    created = (
        await client.put(
            f"/accounts/{credit_id}/credit-terms",
            json={"annual_rate_percent": "24.9", "credit_limit": "100000.00", "grace_days": 55},
        )
    ).json()
    assert Decimal(created["annual_rate_percent"]) == Decimal("24.9")
    assert created["grace_days"] == 55

    # Тот же вызов правит уже существующие условия.
    updated = (
        await client.put(f"/accounts/{credit_id}/credit-terms", json={"annual_rate_percent": "19.5"})
    ).json()
    assert Decimal(updated["annual_rate_percent"]) == Decimal("19.5")
    # Незаданные поля не затираются: правка ставки не должна стирать лимит.
    assert Decimal(updated["credit_limit"]) == Decimal("100000")


async def test_debt_and_available_come_from_the_balance(client: AsyncClient, categories):
    """Долг не хранится отдельно — он и есть отрицательный баланс, только со
    снятым знаком."""
    credit_id = await _credit_account(client)
    await client.put(
        f"/accounts/{credit_id}/credit-terms", json={"credit_limit": "100000.00", "annual_rate_percent": "24.9"}
    )
    await _spend(client, credit_id, "25000.00", categories)

    terms = (await client.get(f"/accounts/{credit_id}/credit-terms")).json()
    assert Decimal(terms["debt"]) == Decimal("25000")
    assert Decimal(terms["available"]) == Decimal("75000")
    assert terms["used_percent"] == 25.0

    # Прикидка процентов: 25000 × 24.9% / 365 × 30 ≈ 511.64.
    assert Decimal(terms["estimated_monthly_interest"]) == Decimal("511.64")


async def test_overspending_the_limit_never_shows_negative_available(client: AsyncClient, categories):
    """Банк иногда пропускает операцию сверх лимита. «Доступно −500»
    бессмысленно: доступного просто нет."""
    credit_id = await _credit_account(client)
    await client.put(f"/accounts/{credit_id}/credit-terms", json={"credit_limit": "10000.00"})
    await _spend(client, credit_id, "12000.00", categories)

    terms = (await client.get(f"/accounts/{credit_id}/credit-terms")).json()
    assert Decimal(terms["debt"]) == Decimal("12000")
    assert Decimal(terms["available"]) == Decimal("0")
    assert terms["used_percent"] == 120.0


async def test_overpaid_credit_has_no_debt(client: AsyncClient, categories):
    """Погасили больше, чем были должны: долг ноль, а не отрицательный."""
    credit_id = await _credit_account(client)
    await client.put(f"/accounts/{credit_id}/credit-terms", json={"annual_rate_percent": "24.9"})
    await client.post(
        "/transactions",
        json={
            "account_id": credit_id,
            "type": "income",
            "amount": "3000.00",
            "description": "Переплата",
            "date": "2026-09-01",
            "category_id": categories["Other Income"]["id"],
        },
    )

    terms = (await client.get(f"/accounts/{credit_id}/credit-terms")).json()
    assert Decimal(terms["debt"]) == Decimal("0")
    # Процентов на нулевой долг не бывает.
    assert terms["estimated_monthly_interest"] is None


async def test_credits_are_listed_worst_first(client: AsyncClient, categories):
    """Список отвечает на вопрос «что гасить в первую очередь»."""
    small = await _credit_account(client, "Маркет Рассрочка")
    big = await _credit_account(client, "Кредитка")
    await client.put(f"/accounts/{small}/credit-terms", json={"annual_rate_percent": "0"})
    await client.put(f"/accounts/{big}/credit-terms", json={"annual_rate_percent": "24.9"})
    await _spend(client, small, "5000.00", categories)
    await _spend(client, big, "40000.00", categories)

    rows = (await client.get("/credits")).json()
    assert [row["account_name"] for row in rows] == ["Кредитка", "Маркет Рассрочка"]

    summary = (await client.get("/credits/summary")).json()
    assert Decimal(summary["debt"]) == Decimal("45000")
    # Беспроцентная рассрочка в стоимость обслуживания не добавляет ничего.
    assert Decimal(summary["estimated_monthly_interest"]) == Decimal("818.63")


async def test_deleting_terms_keeps_the_account_and_its_history(client: AsyncClient, categories):
    """Кредит закрыт — ставка не нужна, но операции остаются: это часть
    того, сколько всё стоило."""
    credit_id = await _credit_account(client)
    await client.put(f"/accounts/{credit_id}/credit-terms", json={"annual_rate_percent": "24.9"})
    await _spend(client, credit_id, "1000.00", categories)

    assert (await client.delete(f"/accounts/{credit_id}/credit-terms")).status_code == 204
    assert (await client.get(f"/accounts/{credit_id}/credit-terms")).status_code == 404

    account = next(row for row in (await client.get("/accounts")).json() if row["id"] == credit_id)
    assert Decimal(account["balance"]) == Decimal("-1000")
    assert len((await client.get("/transactions")).json()["items"]) == 1


async def test_next_payment_date_clamps_to_the_end_of_a_short_month():
    """Тридцать первого февраля не бывает: банк ждёт платёж в последний день
    месяца, а не первого числа следующего."""
    from datetime import date

    from app.services.credit_service import next_payment_date

    assert next_payment_date(31, date(2026, 2, 1)) == date(2026, 2, 28)
    assert next_payment_date(10, date(2026, 2, 10)) == date(2026, 2, 10)
    # Число прошло — платёж в следующем месяце.
    assert next_payment_date(5, date(2026, 2, 10)) == date(2026, 3, 5)
    assert next_payment_date(5, date(2026, 12, 10)) == date(2027, 1, 5)
    assert next_payment_date(None, date(2026, 2, 1)) is None
