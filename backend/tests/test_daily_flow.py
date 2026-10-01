"""Движение денег по дням внутри выбранного месяца.

Дневной ряд приходит в сводке обзора и только для месяца: за год это 365
точек, из которых не прочитать ничего, а ответ втрое тяжелее. Считается он
тем же, чем и месячный, поэтому проверяется главное — что нарезка мельче
не меняет ни сумм, ни правил отбора.
"""
from decimal import Decimal

from httpx import AsyncClient

from tests.helpers import money, txn_payload


async def _summary(client: AsyncClient, year: int, month: int, range_key: str = "month") -> dict:
    resp = await client.get(
        "/dashboard/summary", params={"year": year, "month": month, "range": range_key}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_every_day_of_the_month_is_in_the_row(client: AsyncClient, account_id, categories):
    """Пустые дни остаются в ряду.

    Выбросить их значит сжать календарь: три траты подряд там, где между
    ними неделя, — это уже другой месяц.
    """
    await client.post(
        "/transactions",
        json=txn_payload(account_id, amount="100.00", category_id=categories["Groceries"]["id"], date="2022-03-05"),
    )

    body = await _summary(client, 2022, 3)
    days = body["daily"]
    assert len(days) == 31
    assert days[0]["date"] == "2022-03-01"
    assert days[-1]["date"] == "2022-03-31"
    assert money(days[0]["expense"]) == Decimal("0")
    assert money(days[4]["expense"]) == Decimal("100.00")


async def test_days_add_up_to_the_month(client: AsyncClient, account_id, categories):
    """Сумма дней равна итогу месяца — это одна величина, нарезанная мельче."""
    salary_id = categories["Salary"]["id"]
    groceries_id = categories["Groceries"]["id"]
    await client.post(
        "/transactions",
        json=txn_payload(account_id, amount="50000.00", type="income", category_id=salary_id, date="2022-04-10"),
    )
    await client.post(
        "/transactions",
        json=txn_payload(account_id, amount="1200.50", category_id=groceries_id, date="2022-04-11"),
    )
    await client.post(
        "/transactions",
        json=txn_payload(account_id, amount="800.00", category_id=groceries_id, date="2022-04-25"),
    )

    body = await _summary(client, 2022, 4)
    days = body["daily"]
    assert sum(money(day["income"]) for day in days) == money(body["real_income"])
    assert sum(money(day["expense"]) for day in days) == money(body["spent"])
    assert sum(money(day["net"]) for day in days) == money(body["net"])


async def test_transfers_between_own_accounts_are_not_a_day_of_spending(
    client: AsyncClient, account_id, categories
):
    """Перевод себе деньгами не становится — ни в месяце, ни в дне."""
    other = await client.post("/accounts", json={"name": "Копилка", "kind": "savings", "currency": "RUB"})
    await client.post(
        "/transactions",
        json=txn_payload(
            account_id,
            type="transfer",
            amount="5000.00",
            transfer_account_id=other.json()["id"],
            date="2022-05-12",
        ),
    )

    body = await _summary(client, 2022, 5)
    assert all(money(day["expense"]) == Decimal("0") for day in body["daily"])
    assert all(money(day["income"]) == Decimal("0") for day in body["daily"])


async def test_days_come_only_for_a_month(client: AsyncClient, account_id, categories):
    """За год и за всё время дневного ряда нет: 365 столбцов ничего не говорят."""
    await client.post(
        "/transactions",
        json=txn_payload(account_id, amount="100.00", category_id=categories["Groceries"]["id"], date="2022-06-01"),
    )

    assert (await _summary(client, 2022, 6, "year"))["daily"] == []
    assert (await _summary(client, 2022, 6, "all"))["daily"] == []
    assert (await _summary(client, 2022, 6, "month"))["daily"] != []


async def test_an_excluded_transaction_stays_out_of_the_day(
    client: AsyncClient, account_id, categories
):
    """«Не учитывать» значит не учитывать и здесь: иначе дневной столбец
    спорил бы с месячным на том же обзоре."""
    await client.post(
        "/transactions",
        json=txn_payload(
            account_id,
            amount="700.00",
            category_id=categories["Groceries"]["id"],
            date="2022-07-03",
            is_excluded=True,
        ),
    )

    body = await _summary(client, 2022, 7)
    assert all(money(day["expense"]) == Decimal("0") for day in body["daily"])
