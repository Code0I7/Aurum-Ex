"""Порядок операций внутри дня и баланс счёта после каждой из них.

Проверки написаны вокруг конкретного случая из исходных данных: 26 августа
2024 года там три операции одной датой — приход 12 900, расход 2 000 и
перевод 10 900 на карту. Итог сходится в ноль, но при неудачном порядке
баланс наличных проваливается до −2 000 в день, когда этого не было.
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

DAY = "2024-08-26"


def _txn(account_id: int, **overrides) -> dict:
    payload = {
        "account_id": account_id,
        "type": "expense",
        "amount": "100.00",
        "description": "Операция",
        "date": DAY,
    }
    payload.update(overrides)
    return payload


async def test_day_order_is_assigned_in_entry_sequence(client: AsyncClient, account_id, categories):
    """Номер внутри дня проставляется сам — человеку незачем его набирать."""
    for index in range(3):
        resp = await client.post(
            "/transactions",
            json=_txn(account_id, description=f"Покупка {index}", category_id=categories["Groceries"]["id"]),
        )
        assert resp.status_code == 201

    listing = (await client.get("/transactions", params={"account_id": account_id})).json()["items"]
    # Новое сверху, поэтому порядок в дне убывает.
    assert [row["day_order"] for row in listing] == [2, 1, 0]


async def test_balance_after_each_operation_follows_the_visible_order(client: AsyncClient, account_id, categories):
    """То самое «было 0, стало 500, потом 350, потом 400»."""
    income = categories["Salary"]["id"]
    expense = categories["Groceries"]["id"]

    await client.post("/transactions", json=_txn(account_id, type="income", amount="500.00", category_id=income))
    await client.post("/transactions", json=_txn(account_id, amount="150.00", category_id=expense))
    await client.post("/transactions", json=_txn(account_id, type="income", amount="50.00", category_id=income))

    listing = (await client.get("/transactions", params={"account_id": account_id})).json()["items"]
    # Список идёт от нового к старому, баланс читается снизу вверх.
    assert [row["balance_after"] for row in reversed(listing)] == ["500.00", "350.00", "400.00"]


async def test_balance_starts_from_the_accounts_opening_balance(client: AsyncClient, categories):
    """Начальный остаток — часть баланса, но не доход: он появляется в
    колонке баланса и не появляется в доходах."""
    account = (
        await client.post(
            "/accounts",
            json={"name": "С остатком", "kind": "checking", "opening_balance": "1000.00", "opening_date": DAY},
        )
    ).json()

    await client.post(
        "/transactions",
        json=_txn(account["id"], amount="250.00", category_id=categories["Groceries"]["id"]),
    )

    listing = (await client.get("/transactions", params={"account_id": account["id"]})).json()["items"]
    assert listing[0]["balance_after"] == "750.00"


async def test_balance_is_computed_over_history_not_over_the_filtered_page(
    client: AsyncClient, account_id, categories
):
    """Фильтр сужает список, но не переписывает баланс: показать «350» там,
    где предыдущие операции просто скрыты, — значит показать неправду."""
    income = categories["Salary"]["id"]
    expense = categories["Groceries"]["id"]

    await client.post("/transactions", json=_txn(account_id, type="income", amount="500.00", category_id=income))
    await client.post("/transactions", json=_txn(account_id, amount="150.00", category_id=expense))

    # Видна только трата, но её баланс всё равно учитывает предшествующий доход.
    filtered = (
        await client.get("/transactions", params={"account_id": account_id, "type": "expense"})
    ).json()["items"]
    assert len(filtered) == 1
    assert filtered[0]["balance_after"] == "350.00"


async def test_excluded_transactions_do_not_move_the_balance(client: AsyncClient, account_id, categories):
    """Возвращённый товар остаётся в истории, но денег не двигает."""
    income = categories["Salary"]["id"]
    expense = categories["Groceries"]["id"]

    await client.post("/transactions", json=_txn(account_id, type="income", amount="500.00", category_id=income))
    await client.post(
        "/transactions",
        json=_txn(account_id, amount="150.00", category_id=expense, is_excluded=True),
    )

    listing = (await client.get("/transactions", params={"account_id": account_id})).json()["items"]
    assert listing[0]["is_excluded"] is True
    assert listing[0]["balance_after"] == "500.00"


async def test_reorder_moves_a_row_within_its_day(client: AsyncClient, account_id, categories):
    """Записал вечером по памяти и перепутал последовательность — строка
    перетаскивается, и баланс пересчитывается под новый порядок."""
    income = categories["Salary"]["id"]
    expense = categories["Groceries"]["id"]

    spend = (
        await client.post("/transactions", json=_txn(account_id, amount="150.00", category_id=expense))
    ).json()
    await client.post("/transactions", json=_txn(account_id, type="income", amount="500.00", category_id=income))

    # Сейчас трата идёт первой и уводит счёт в минус.
    before = (await client.get("/transactions", params={"account_id": account_id})).json()["items"]
    assert [row["balance_after"] for row in reversed(before)] == ["-150.00", "350.00"]

    resp = await client.post(f"/transactions/{spend['id']}/reorder", json={"position": 1})
    assert resp.status_code == 200

    after = (await client.get("/transactions", params={"account_id": account_id})).json()["items"]
    assert [row["balance_after"] for row in reversed(after)] == ["500.00", "350.00"]


async def test_reorder_clamps_a_position_past_the_end(client: AsyncClient, account_id, categories):
    """Бросок мимо цели не должен оборачиваться сообщением об ошибке."""
    first = (
        await client.post(
            "/transactions", json=_txn(account_id, category_id=categories["Groceries"]["id"])
        )
    ).json()
    await client.post("/transactions", json=_txn(account_id, category_id=categories["Groceries"]["id"]))

    resp = await client.post(f"/transactions/{first['id']}/reorder", json={"position": 99})
    assert resp.status_code == 200
    assert resp.json()["day_order"] == 1


async def test_transfer_credits_the_destination_account_balance(client: AsyncClient, account_id, categories):
    """У строки перевода счёт-получатель лежит в другой колонке, поэтому
    приход на него считается отдельно — проверяем, что он не потерялся."""
    destination = (await client.post("/accounts", json={"name": "Наличные", "kind": "cash"})).json()

    await client.post(
        "/transactions",
        json=_txn(account_id, type="income", amount="500.00", category_id=categories["Salary"]["id"]),
    )
    await client.post(
        "/transactions",
        json=_txn(account_id, type="transfer", amount="200.00", transfer_account_id=destination["id"], category_id=None),
    )
    await client.post(
        "/transactions",
        json=_txn(destination["id"], amount="50.00", category_id=categories["Groceries"]["id"]),
    )

    listing = (await client.get("/transactions", params={"account_id": destination["id"]})).json()["items"]
    # В выписку счёта попадают обе стороны перевода: и уход, и приход. Без
    # этого половина движений между двумя своими счетами не видна.
    assert len(listing) == 2

    # 200 пришло переводом, 50 потрачено. Баланс считается для счёта, по
    # которому фильтруем: у строки перевода иначе стоял бы остаток
    # отправителя, и деньги выглядели бы взявшимися ниоткуда.
    by_amount = {item["amount"]: item for item in listing}
    assert by_amount["200.00"]["balance_after"] == "200.00"
    assert by_amount["50.00"]["balance_after"] == "150.00"
