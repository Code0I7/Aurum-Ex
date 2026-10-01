"""Дашборд за месяц, год и всё время.

Месяц как единственная рамка — то, чем неудобна была исходная таблица:
годовые итоги приходилось собирать отдельным листом, а вопрос «сколько всего
заработано за четыре года» не имел ответа вовсе.
"""
from decimal import Decimal

from httpx import AsyncClient


async def _spend(client: AsyncClient, account_id, categories, amount: str, date: str, description="Покупка"):
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": amount,
            "description": description,
            "date": date,
            "category_id": categories["Groceries"]["id"],
        },
    )
    assert resp.status_code == 201, resp.text


async def _earn(client: AsyncClient, account_id, categories, amount: str, date: str):
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "income",
            "amount": amount,
            "description": "Зарплата",
            "date": date,
            "category_id": categories["Salary"]["id"],
        },
    )
    assert resp.status_code == 201, resp.text


async def test_period_widens_from_month_to_year_to_everything(client: AsyncClient, account_id, categories):
    await _earn(client, account_id, categories, "40000.00", "2025-06-10")
    await _earn(client, account_id, categories, "50000.00", "2026-03-10")
    await _earn(client, account_id, categories, "60000.00", "2026-07-10")

    month = (await client.get("/dashboard/summary?year=2026&month=3&range=month")).json()
    assert Decimal(month["real_income"]) == Decimal("50000")
    assert month["start_date"] == "2026-03-01"
    assert month["end_date"] == "2026-03-31"

    year = (await client.get("/dashboard/summary?year=2026&range=year")).json()
    assert Decimal(year["real_income"]) == Decimal("110000")

    everything = (await client.get("/dashboard/summary?range=all")).json()
    assert Decimal(everything["real_income"]) == Decimal("150000")
    # За всё время границы берутся из данных: «с 1970 года» — не ответ.
    assert everything["start_date"] == "2025-06-10"
    assert everything["end_date"] == "2026-07-10"


async def test_all_time_starts_at_the_earliest_opening_balance(client: AsyncClient, categories):
    """Счёт мог быть открыт раньше первой записи. Объявить началом истории
    момент, когда деньги на счёте уже лежали, — неправда."""
    account = (
        await client.post(
            "/accounts",
            json={
                "name": "Карта",
                "kind": "checking",
                "currency": "RUB",
                "opening_balance": "5210.40",
                "opening_date": "2022-08-28",
            },
        )
    ).json()
    await client.post(
        "/transactions",
        json={
            "account_id": account["id"],
            "type": "income",
            "amount": "100.00",
            "description": "Первая запись",
            "date": "2022-08-31",
            "category_id": categories["Salary"]["id"],
        },
    )

    data = (await client.get("/dashboard/summary?range=all")).json()
    assert data["start_date"] == "2022-08-28"


async def test_month_stays_the_default(client: AsyncClient, account_id, categories):
    """Эндпоинт не должен молча менять смысл ответа для того, кто просто
    передал год и месяц."""
    await _earn(client, account_id, categories, "40000.00", "2026-03-10")
    await _earn(client, account_id, categories, "50000.00", "2026-04-10")

    data = (await client.get("/dashboard/summary?year=2026&month=3")).json()
    assert Decimal(data["real_income"]) == Decimal("40000")


async def test_account_balances_are_current_regardless_of_period(client: AsyncClient, account_id, categories):
    """Вопрос «сколько у меня сейчас» от выбора периода не зависит."""
    await _earn(client, account_id, categories, "40000.00", "2025-06-10")
    await _spend(client, account_id, categories, "5000.00", "2026-03-10")

    for query in ("range=all", "year=2025&month=6&range=month", "year=2026&range=year"):
        data = (await client.get(f"/dashboard/summary?{query}")).json()
        account = next(row for row in data["accounts"] if row["account_id"] == account_id)
        assert Decimal(account["balance"]) == Decimal("35000"), query


async def test_reserved_and_available_appear_next_to_the_balance(client: AsyncClient, account_id, categories):
    await _earn(client, account_id, categories, "40000.00", "2026-03-10")
    goal = (
        await client.post(
            "/goals", json={"name": "Отпуск", "target_amount": "60000.00", "account_id": account_id}
        )
    ).json()
    await client.post(f"/goals/{goal['id']}/contributions", json={"amount": "9000.00", "date": "2026-03-11"})

    data = (await client.get("/dashboard/summary?range=all")).json()
    account = next(row for row in data["accounts"] if row["account_id"] == account_id)
    assert Decimal(account["reserved"]) == Decimal("9000")
    assert Decimal(account["available"]) == Decimal("31000")


async def test_hourly_earnings_need_hours_to_exist(client: AsyncClient, account_id, categories):
    """Смысл не в самой цифре, а в переводе покупок на язык времени. Делить
    на ноль нечестнее, чем не показывать."""
    await _earn(client, account_id, categories, "40000.00", "2026-03-10")

    data = (await client.get("/dashboard/summary?year=2026&month=3&range=month")).json()
    assert data["hours_worked"] is None
    assert data["earned_per_hour"] is None

    await client.put("/work-periods", json={"year": 2026, "month": 3, "hours": "160.00", "workdays": 20})
    data = (await client.get("/dashboard/summary?year=2026&month=3&range=month")).json()
    assert Decimal(data["hours_worked"]) == Decimal("160")
    assert Decimal(data["earned_per_hour"]) == Decimal("250")
    # Копейки, а не хвост из двадцати знаков: округлять должно одно место.
    assert data["earned_per_hour"].count(".") == 1
    assert len(data["earned_per_hour"].split(".")[1]) == 2


async def test_hours_outside_the_period_are_not_counted(client: AsyncClient, account_id, categories):
    await _earn(client, account_id, categories, "40000.00", "2026-03-10")
    await client.put("/work-periods", json={"year": 2026, "month": 3, "hours": "160.00"})
    await client.put("/work-periods", json={"year": 2026, "month": 8, "hours": "100.00"})

    march = (await client.get("/dashboard/summary?year=2026&month=3&range=month")).json()
    assert Decimal(march["hours_worked"]) == Decimal("160")

    year = (await client.get("/dashboard/summary?year=2026&range=year")).json()
    assert Decimal(year["hours_worked"]) == Decimal("260")


async def test_largest_expenses_explain_the_period(client: AsyncClient, account_id, categories):
    """Круг из восьми долей отвечает «на что вообще», а этот список — «из-за
    чего именно в этом месяце»."""
    await _spend(client, account_id, categories, "17273.00", "2026-03-05", "Монитор")
    await _spend(client, account_id, categories, "5690.00", "2026-03-06", "Кронштейн")
    await _spend(client, account_id, categories, "252.00", "2026-03-07", "Стекло")
    # Из другого месяца — в список марта попасть не должна.
    await _spend(client, account_id, categories, "99999.00", "2026-04-01", "Не тот месяц")

    data = (await client.get("/dashboard/summary?year=2026&month=3&range=month")).json()
    assert [row["description"] for row in data["largest_expenses"]] == ["Монитор", "Кронштейн", "Стекло"]
    assert Decimal(data["largest_expenses"][0]["amount"]) == Decimal("17273")


async def test_excluded_rows_stay_out_of_the_largest_list(client: AsyncClient, account_id, categories):
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "99999.00",
            "description": "Отменено",
            "date": "2026-03-05",
            "category_id": categories["Groceries"]["id"],
            "is_excluded": True,
        },
    )
    assert resp.status_code == 201
    await _spend(client, account_id, categories, "100.00", "2026-03-06", "Настоящая")

    data = (await client.get("/dashboard/summary?year=2026&month=3&range=month")).json()
    assert [row["description"] for row in data["largest_expenses"]] == ["Настоящая"]


async def test_monthly_series_matches_the_cash_flow_page(client: AsyncClient, account_id, categories):
    """Два разных ответа на один вопрос — худшее, что приложение может
    показать про деньги."""
    await _earn(client, account_id, categories, "40000.00", "2026-03-10")
    await _spend(client, account_id, categories, "5000.00", "2026-04-10")

    dashboard = (await client.get("/dashboard/summary?year=2026&range=year")).json()
    cash_flow = (await client.get("/cash-flow?start_date=2026-01-01&end_date=2026-12-31")).json()

    assert [(p["year"], p["month"], p["income"], p["expense"]) for p in dashboard["monthly"]] == [
        (p["year"], p["month"], p["income"], p["expense"]) for p in cash_flow["points"]
    ]


async def test_an_empty_installation_still_shows_its_accounts(client: AsyncClient):
    """Счёт может существовать с начальным остатком и без единой записи."""
    await client.post(
        "/accounts",
        json={"name": "Копилка", "kind": "savings", "currency": "RUB", "opening_balance": "5000.00"},
    )

    data = (await client.get("/dashboard/summary?range=all")).json()
    assert data["start_date"] is None
    assert Decimal(data["real_income"]) == Decimal("0")
    balances = {row["name"]: Decimal(row["balance"]) for row in data["accounts"]}
    assert balances["Копилка"] == Decimal("5000")
