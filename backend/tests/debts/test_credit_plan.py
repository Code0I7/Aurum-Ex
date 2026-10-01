"""Калькулятор кредита и минимальный платёж правилом.

Проверяется то, ради чего калькулятор и нужен: что «платить минимальный»
выходит в разы дороже, что платёж меньше процентов честно называется
бесконечным, и что правило «8%, но не меньше 600» считается как правило, а
не как одно из двух чисел.
"""
from decimal import Decimal

from httpx import AsyncClient

from app.services.credit_plan_service import annuity_payment, minimum_payment_for

# Пометки asyncio нет намеренно: режим auto в pytest.ini включает её сам, а
# проставленная руками она ругается на синхронные тесты формул.


def test_annuity_matches_the_formula_from_the_contract():
    # 100 000 под 12% на 12 месяцев — хрестоматийные 8 884,88, округлённые
    # вверх до рубля, как это делают в договорах.
    assert annuity_payment(Decimal("100000"), Decimal("12"), 12) == Decimal("8885")


def test_annuity_without_interest_is_plain_division():
    """Нулевая ставка — не частный случай формулы, а деление.

    В самой формуле при нулевой ставке знаменатель обращается в ноль, и
    рассрочка под 0% уронила бы расчёт.
    """
    assert annuity_payment(Decimal("30000"), Decimal("0"), 6) == Decimal("5000.00")


def test_minimum_payment_follows_the_rule():
    # 8% от 40 000 — это 3 200, порог не при чём.
    assert minimum_payment_for(Decimal("40000"), Decimal("8"), Decimal("600")) == Decimal("3200.00")
    # 8% от 5 000 — 400, и тогда работает порог.
    assert minimum_payment_for(Decimal("5000"), Decimal("8"), Decimal("600")) == Decimal("600.00")
    # Долга нет — и правила нет.
    assert minimum_payment_for(Decimal("0"), Decimal("8"), Decimal("600")) is None
    # Ни доли, ни порога: выдумывать нечего.
    assert minimum_payment_for(Decimal("1000"), None, None) is None
    # Остаток меньше порога: платить больше долга банк не просит.
    assert minimum_payment_for(Decimal("300"), Decimal("8"), Decimal("600")) == Decimal("300.00")


async def test_plan_shows_the_price_of_paying_the_minimum(client: AsyncClient):
    resp = await client.post(
        "/credits/plan",
        json={
            "amount": "40000",
            "annual_rate_percent": "39.9",
            "minimum_percent": "8",
            "minimum_floor": "600",
            "target_months": 12,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    minimum = body["minimum"]
    recommended = body["recommended"]

    # Минимальный платёж в первый месяц — 8% от сорока тысяч.
    assert Decimal(minimum["first_payment"]) == Decimal("3200.00")
    # Долг гасится, но медленно и дорого.
    assert not minimum["never_closes"]
    assert minimum["months"] > 12
    assert Decimal(minimum["total_interest"]) > Decimal(recommended["total_interest"])
    # За год по рекомендуемому платежу — заметно дешевле.
    assert recommended["months"] == 12
    assert Decimal(recommended["payment"]) > Decimal("4000")
    # Закрыть в льготный период — ровно сумма покупки, без процентов.
    assert Decimal(body["in_grace"]) == Decimal("40000.00")


async def test_plan_admits_a_payment_that_never_closes(client: AsyncClient):
    """Платёж меньше процентов — долг не уменьшается никогда.

    Считать такой случай «очень долгим» нельзя: человек прочтёт число
    месяцев и решит, что конец всё-таки наступит.
    """
    resp = await client.post(
        "/credits/plan",
        json={"amount": "100000", "annual_rate_percent": "60", "fixed_payment": "1000"},
    )
    assert resp.status_code == 200, resp.text
    fixed = resp.json()["fixed"]
    assert fixed["never_closes"] is True
    assert fixed["months"] == 0


async def test_plan_without_a_rule_returns_no_minimum(client: AsyncClient):
    resp = await client.post(
        "/credits/plan", json={"amount": "10000", "annual_rate_percent": "0", "target_months": 5}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["minimum"] is None
    assert body["recommended"]["months"] == 5
    # Рассрочка под ноль: сколько взял, столько и отдал.
    assert Decimal(body["recommended"]["total_interest"]) == Decimal("0")
    assert Decimal(body["recommended"]["total_paid"]) == Decimal("10000.00")


async def test_terms_keep_a_rate_matrix(client: AsyncClient):
    """Ставок в тарифе семь, и они должны сохраняться все."""
    account = (
        await client.post(
            "/accounts", json={"name": "Кредитка", "kind": "credit_card", "currency": "RUB"}
        )
    ).json()
    resp = await client.put(
        f"/accounts/{account['id']}/credit-terms",
        json={
            "annual_rate_percent": "39.9",
            "credit_limit": "127000",
            "grace_days": 55,
            "minimum_payment_percent": "8",
            "minimum_payment": "600",
            "rates": [
                {"name": "Покупки", "percent": "39.9", "condition": "с 31-го дня"},
                {"name": "Снятие наличных", "percent": "59.9", "condition": "с 31-го дня"},
                {"name": "Покупки", "percent": "0", "condition": "в льготный период"},
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [rate["name"] for rate in body["rates"]] == ["Покупки", "Снятие наличных", "Покупки"]
    assert Decimal(body["rates"][1]["percent"]) == Decimal("59.9")

    # Повторное сохранение заменяет матрицу целиком, а не добавляет строки.
    resp = await client.put(
        f"/accounts/{account['id']}/credit-terms",
        json={"rates": [{"name": "Покупки", "percent": "39.9"}]},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["rates"]) == 1
    # Остальные условия при этом на месте.
    assert Decimal(resp.json()["credit_limit"]) == Decimal("127000.00")


async def test_terms_save_with_only_a_few_fields(client: AsyncClient):
    """Ставка, лимит и льготный период — и больше ничего.

    Ровно так их и заводят в первый раз: дату платежа человек посмотрит в
    выписке позже, а минимального платежа у рассрочки нет вовсе.
    """
    account = (
        await client.post(
            "/accounts", json={"name": "Рассрочка", "kind": "loan", "currency": "RUB"}
        )
    ).json()
    resp = await client.put(
        f"/accounts/{account['id']}/credit-terms",
        json={"annual_rate_percent": "0", "credit_limit": "100000", "grace_days": 120},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["payment_day"] is None
    assert body["minimum_payment_due"] is None
    assert body["rates"] == []


async def test_minimum_payment_due_follows_the_debt(client: AsyncClient):
    account = (
        await client.post(
            "/accounts", json={"name": "Кредитка", "kind": "credit_card", "currency": "RUB"}
        )
    ).json()
    await client.put(
        f"/accounts/{account['id']}/credit-terms",
        json={"minimum_payment_percent": "8", "minimum_payment": "600"},
    )
    await client.post(
        "/transactions",
        json={
            "account_id": account["id"],
            "type": "expense",
            "amount": "40000.00",
            "date": "2026-02-10",
        },
    )
    terms = (await client.get(f"/accounts/{account['id']}/credit-terms")).json()
    assert Decimal(terms["debt"]) == Decimal("40000.00")
    assert Decimal(terms["minimum_payment_due"]) == Decimal("3200.00")

async def test_plan_puts_the_operation_fee_into_the_debt(client: AsyncClient):
    """Снять 127 000 и быть должным 127 000 — разные вещи.

    Плата за снятие («2,9% плюс 290 ₽») списывается в день операции и
    ложится в тот же долг, поэтому проценты идут уже и на неё.
    """
    resp = await client.post(
        "/credits/plan",
        json={
            "amount": "127000",
            "annual_rate_percent": "59.9",
            "fee_percent": "2.9",
            "fee_fixed": "290",
            "target_months": 12,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # 2,9% от 127 000 — это 3 683, плюс 290 фиксированных.
    assert Decimal(body["fee"]) == Decimal("3973.00")
    assert Decimal(body["amount_with_fee"]) == Decimal("130973.00")
    # Закрыть сразу — тоже с комиссией: её платят в любом случае.
    assert Decimal(body["in_grace"]) == Decimal("130973.00")
    # И проценты считаются от долга с комиссией, а не от запрошенной суммы.
    assert Decimal(body["recommended"]["total_paid"]) > Decimal("130973.00")


async def test_plan_without_a_fee_is_unchanged(client: AsyncClient):
    """Комиссии нет — ответ такой же, как был до её появления."""
    resp = await client.post(
        "/credits/plan", json={"amount": "10000", "annual_rate_percent": "0", "target_months": 5}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(body["fee"]) == Decimal("0")
    assert Decimal(body["amount_with_fee"]) == Decimal("10000.00")
