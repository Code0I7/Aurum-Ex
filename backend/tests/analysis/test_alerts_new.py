"""Оповещения о новых разделах.

Оповещение имеет смысл ровно тогда, когда о проблеме иначе не узнаешь.
Поэтому каждое из трёх проверяется парой: сработало там, где должно, и
промолчало там, где не должно. Оповещение, которое горит всегда, человек
перестаёт читать через неделю.
"""
from datetime import date, timedelta
from decimal import Decimal

from httpx import AsyncClient


def _keys(alerts: dict) -> set[str]:
    return {alert["key"] for alert in alerts["alerts"]}


async def _credit_with_debt(client: AsyncClient, categories, payment_day: int) -> dict:
    account = (
        await client.post("/accounts", json={"name": "Кредитка", "kind": "credit_card", "currency": "RUB"})
    ).json()
    await client.put(
        f"/accounts/{account['id']}/credit-terms",
        json={"annual_rate_percent": "24.9", "payment_day": payment_day},
    )
    await client.post(
        "/transactions",
        json={
            "account_id": account["id"],
            "type": "expense",
            "amount": "12000.00",
            "description": "Покупка",
            "date": date.today().isoformat(),
            "category_id": categories["Groceries"]["id"],
        },
    )
    return account


async def test_a_credit_payment_coming_up_is_announced(client: AsyncClient, categories):
    """Единственное оповещение о дате, а не о тенденции: пропущенный платёж
    стоит пени сразу."""
    soon = date.today() + timedelta(days=3)
    await _credit_with_debt(client, categories, soon.day)

    assert "credit_payment_due" in _keys((await client.get("/insights/alerts")).json())


async def test_a_repaid_credit_stays_quiet(client: AsyncClient, categories):
    """Долг ноль означает, что платить нечего, и напоминание было бы шумом."""
    soon = date.today() + timedelta(days=3)
    account = (
        await client.post("/accounts", json={"name": "Кредитка", "kind": "credit_card", "currency": "RUB"})
    ).json()
    await client.put(
        f"/accounts/{account['id']}/credit-terms", json={"payment_day": soon.day}
    )

    assert "credit_payment_due" not in _keys((await client.get("/insights/alerts")).json())


async def test_a_distant_payment_stays_quiet(client: AsyncClient, categories):
    """Оповещение, которое горит всегда, перестают читать через неделю."""
    far = date.today() + timedelta(days=20)
    # Числа за пределами месяца прижимаются к его длине, поэтому берём день,
    # который заведомо ещё не наступил и до которого больше недели.
    if far.month != date.today().month:
        far = date.today() + timedelta(days=15)
    await _credit_with_debt(client, categories, far.day)

    alerts = (await client.get("/insights/alerts")).json()
    due = [alert for alert in alerts["alerts"] if alert["key"] == "credit_payment_due"]
    assert due == [] or due[0]["params"]["days"] > 7


async def test_a_goal_without_an_account_is_pointed_out(client: AsyncClient, account_id):
    """Такая цель считается, но счёт не покажет «отложено»: тихая
    половинчатость хуже явной."""
    await client.post("/goals", json={"name": "Мечта", "target_amount": "50000.00"})
    assert "goal_without_account" in _keys((await client.get("/insights/alerts")).json())

    # Привязали к счёту — оповещение уходит.
    goals = (await client.get("/goals")).json()
    await client.patch(f"/goals/{goals[0]['id']}", json={"account_id": account_id})
    assert "goal_without_account" not in _keys((await client.get("/insights/alerts")).json())


async def test_an_oversold_holding_is_pointed_out(client: AsyncClient):
    """Прибыль по такой позиции завышена, и молчать об этом нельзя."""
    portfolio = (await client.post("/investments/portfolios", json={"name": "Долгосрок"})).json()
    holding = (
        await client.post(
            "/investments/holdings",
            json={"portfolio_id": portfolio["id"], "name": "ACME", "kind": "stock", "currency": "RUB"},
        )
    ).json()
    await client.post(
        f"/investments/holdings/{holding['id']}/trades",
        json={"side": "buy", "quantity": "2", "price_per_unit": "100", "trade_date": "2026-01-10"},
    )
    assert "investment_oversold" not in _keys((await client.get("/insights/alerts")).json())

    await client.post(
        f"/investments/holdings/{holding['id']}/trades",
        json={"side": "sell", "quantity": "5", "price_per_unit": "150", "trade_date": "2026-02-10"},
    )
    alerts = (await client.get("/insights/alerts")).json()
    assert "investment_oversold" in _keys(alerts)
    oversold = next(item for item in alerts["alerts"] if item["key"] == "investment_oversold")
    assert oversold["params"]["count"] == 1


async def test_a_clean_install_raises_nothing_new(client: AsyncClient):
    """Пустая установка не должна встречать человека тремя предупреждениями
    ни о чём."""
    keys = _keys((await client.get("/insights/alerts")).json())
    assert "credit_payment_due" not in keys
    assert "goal_without_account" not in keys
    assert "investment_oversold" not in keys
