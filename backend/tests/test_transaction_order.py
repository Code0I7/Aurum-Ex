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


async def test_day_order_spans_accounts_so_cash_can_be_moved_above_a_card(
    client: AsyncClient, account_id, categories
):
    """Покупку наличными нельзя было поднять выше карточной того же дня.

    Нумерация шла внутри счёта, и у первой операции каждого счёта был один
    и тот же номер: список сортируется по нему, а он совпадал. Теперь номер
    сквозной по дню — счета в списке идут вперемешку, и порядок дня должен
    быть тем, что человек видит.
    """
    cash = (await client.post("/accounts", json={"name": "Наличные", "kind": "cash"})).json()
    groceries = categories["Groceries"]["id"]

    card_spend = (
        await client.post(
            "/transactions", json=_txn(account_id, description="Картой", category_id=groceries)
        )
    ).json()
    cash_spend = (
        await client.post(
            "/transactions",
            json=_txn(cash["id"], description="Наличными", category_id=groceries),
        )
    ).json()

    # Номера не совпадают: иначе переставлять было бы нечего.
    assert card_spend["day_order"] != cash_spend["day_order"]

    # Наличная запись поднимается над карточной.
    resp = await client.post(f"/transactions/{cash_spend['id']}/reorder", json={"position": 0})
    assert resp.status_code == 200, resp.text

    listing = (await client.get("/transactions")).json()["items"]
    assert [row["description"] for row in listing] == ["Картой", "Наличными"]


async def test_reorder_across_accounts_keeps_each_balance(client: AsyncClient, account_id, categories):
    """Сквозная нумерация дня не должна трогать балансы: они считаются с
    разбиением по счёту, и относительный порядок внутри счёта пересчёт
    сохраняет."""
    cash = (await client.post("/accounts", json={"name": "Наличные", "kind": "cash"})).json()
    income = categories["Salary"]["id"]
    expense = categories["Groceries"]["id"]

    await client.post("/transactions", json=_txn(account_id, type="income", amount="500.00", category_id=income))
    await client.post("/transactions", json=_txn(account_id, amount="150.00", category_id=expense))
    cash_spend = (
        await client.post("/transactions", json=_txn(cash["id"], amount="40.00", category_id=expense))
    ).json()

    await client.post(f"/transactions/{cash_spend['id']}/reorder", json={"position": 0})

    card = (await client.get("/transactions", params={"account_id": account_id})).json()["items"]
    assert [row["balance_after"] for row in reversed(card)] == ["500.00", "350.00"]
    cash_rows = (await client.get("/transactions", params={"account_id": cash["id"]})).json()["items"]
    assert [row["balance_after"] for row in cash_rows] == ["-40.00"]


async def test_a_block_of_rows_moves_as_one(client: AsyncClient, account_id, categories):
    """Свёрнутая группа «Автобус ×3» — одна строка на экране и три записи в
    базе. По одной их двигать нельзя: после первой же перестановки
    нумерация меняется, и остальные уезжают не туда."""
    groceries = categories["Groceries"]["id"]
    rides = [
        (
            await client.post(
                "/transactions",
                json=_txn(account_id, amount="40.00", description="Автобус", category_id=groceries),
            )
        ).json()
        for _ in range(3)
    ]
    coffee = (
        await client.post(
            "/transactions", json=_txn(account_id, amount="200.00", description="Кофе", category_id=groceries)
        )
    ).json()

    # Порядок дня сейчас: автобус, автобус, автобус, кофе.
    assert coffee["day_order"] == 3

    resp = await client.post(
        "/transactions/reorder-block",
        json={"ids": [ride["id"] for ride in rides], "position": 1},
    )
    assert resp.status_code == 204, resp.text

    listing = (await client.get("/transactions")).json()["items"]
    # Показ идёт от новых к старым, поэтому в дне порядок обратный.
    assert [row["description"] for row in reversed(listing)] == ["Кофе", "Автобус", "Автобус", "Автобус"]
    assert [row["day_order"] for row in reversed(listing)] == [0, 1, 2, 3]


async def test_a_block_keeps_its_own_order(client: AsyncClient, account_id, categories):
    """Внутри блока порядок сохраняется в том виде, в каком его прислали."""
    groceries = categories["Groceries"]["id"]
    first, second = [
        (
            await client.post(
                "/transactions",
                json=_txn(account_id, amount="40.00", description=f"Поездка {index}", category_id=groceries),
            )
        ).json()
        for index in range(2)
    ]
    await client.post(
        "/transactions", json=_txn(account_id, description="Кофе", category_id=groceries)
    )

    resp = await client.post(
        "/transactions/reorder-block", json={"ids": [first["id"], second["id"]], "position": 1}
    )
    assert resp.status_code == 204, resp.text

    listing = (await client.get("/transactions")).json()["items"]
    assert [row["description"] for row in reversed(listing)] == ["Кофе", "Поездка 0", "Поездка 1"]


async def test_a_block_from_two_days_is_rejected(client: AsyncClient, account_id, categories):
    """Между днями записи не переносятся: дату меняют редактированием даты."""
    groceries = categories["Groceries"]["id"]
    today = (
        await client.post("/transactions", json=_txn(account_id, category_id=groceries))
    ).json()
    other = (
        await client.post(
            "/transactions", json=_txn(account_id, date="2024-08-27", category_id=groceries)
        )
    ).json()

    resp = await client.post(
        "/transactions/reorder-block", json={"ids": [today["id"], other["id"]], "position": 0}
    )
    assert resp.status_code == 400


async def test_a_block_with_an_unknown_row_is_rejected(client: AsyncClient, account_id, categories):
    known = (
        await client.post(
            "/transactions", json=_txn(account_id, category_id=categories["Groceries"]["id"])
        )
    ).json()
    resp = await client.post(
        "/transactions/reorder-block", json={"ids": [known["id"], 999_999], "position": 0}
    )
    assert resp.status_code == 404

async def test_incoming_transfer_sits_where_the_list_shows_it(client: AsyncClient, account_id, categories):
    """Приход по переводу учитывается там, где строка стоит в списке.

    Случай, на котором «баланс после» и разъезжался с реальностью: в один
    день перевод введён раньше соседней операции, а показан ниже неё —
    после перестановки внутри дня. Пока приход искали по порядку ввода, а
    список шёл по порядку показа, колонка прыгала вверх и возвращалась: в
    ней стояли суммы, которых на счёте не было.
    """
    other = (
        await client.post("/accounts", json={"name": "Копилка", "kind": "savings", "currency": "RUB"})
    ).json()

    # Покупка введена первой, перевод — вторым, поэтому id у перевода
    # больше.
    purchase = (
        await client.post(
            "/transactions",
            json=_txn(account_id, amount="300.00", category_id=categories["Groceries"]["id"]),
        )
    ).json()
    transfer = (
        await client.post(
            "/transactions",
            json={
                "account_id": other["id"],
                "type": "transfer",
                "amount": "1000.00",
                "transfer_account_id": account_id,
                "date": DAY,
            },
        )
    ).json()

    # А человек перетащил перевод в начало дня: теперь он показан ниже
    # покупки, хотя введён позже. Порядок показа и порядок ввода разошлись.
    moved = await client.post(f"/transactions/{transfer['id']}/reorder", json={"position": 0})
    assert moved.status_code == 200, moved.text

    listing = (await client.get("/transactions", params={"account_id": account_id})).json()["items"]
    # Сверху новое: покупка, под ней перевод.
    assert [row["id"] for row in listing] == [purchase["id"], transfer["id"]]

    # Читаем снизу вверх, как деньги и двигались: пришла тысяча, ушли триста.
    # До исправления в верхней строке стояло −300: приход искали по порядку
    # ввода и для покупки не засчитывали, хотя в списке он стоит ниже неё.
    assert [row["balance_after"] for row in reversed(listing)] == ["1000.00", "700.00"]

