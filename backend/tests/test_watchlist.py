"""Список наблюдения — то, чем в исходной таблице был лист «Отследить».

Там выбирали несколько подкатегорий и выписывали их по месяцам руками.
Здесь проверяется, что отметки на категории достаточно: суммы собираются
по всей ветке, прошлый год стоит рядом, а неотмеченные категории в список
не попадают — иначе он ничем не отличался бы от таблицы года.
"""
from decimal import Decimal

from httpx import AsyncClient

from tests.helpers import txn_payload


async def _watch(client: AsyncClient, category_id: int) -> None:
    resp = await client.patch(f"/categories/{category_id}", json={"is_watched": True})
    assert resp.status_code == 200, resp.text


def _row(watchlist: dict, name: str) -> dict:
    return next(row for row in watchlist["rows"] if row["name"] == name)


async def test_only_watched_categories_appear(client: AsyncClient, account_id, categories):
    """Смысл списка в том, что в нём мало строк."""
    await client.post(
        "/transactions",
        json=txn_payload(account_id, amount="500.00", category_id=categories["Groceries"]["id"]),
    )
    await client.post(
        "/transactions",
        json=txn_payload(account_id, amount="300.00", category_id=categories["Shopping"]["id"]),
    )

    empty = (await client.get("/plans/watchlist?year=2026")).json()
    assert empty["rows"] == []

    await _watch(client, categories["Groceries"]["id"])
    watchlist = (await client.get("/plans/watchlist?year=2026")).json()
    assert [row["name"] for row in watchlist["rows"]] == ["Groceries"]
    assert Decimal(_row(watchlist, "Groceries")["months"][0]) == Decimal("500")
    assert Decimal(_row(watchlist, "Groceries")["total"]) == Decimal("500")


async def test_watched_branch_includes_categories_two_levels_below(
    client: AsyncClient, account_id, categories
):
    """Отметив «Продукты», человек хочет видеть и сыр, лежащий двумя
    уровнями ниже, — иначе отметка на ветке ничего не значила бы."""
    parent = categories["Groceries"]["id"]
    dairy = (
        await client.post(
            "/categories",
            json={"name": "Молочное", "kind": "expense", "color": "#aabbcc", "parent_id": parent},
        )
    ).json()
    cheese = (
        await client.post(
            "/categories",
            json={"name": "Сыр", "kind": "expense", "color": "#aabbcc", "parent_id": dairy["id"]},
        )
    ).json()

    await client.post(
        "/transactions", json=txn_payload(account_id, amount="200.00", category_id=cheese["id"])
    )
    await client.post(
        "/transactions", json=txn_payload(account_id, amount="50.00", category_id=parent)
    )

    await _watch(client, parent)
    watchlist = (await client.get("/plans/watchlist?year=2026")).json()
    row = _row(watchlist, "Groceries")
    # 200 у внука плюс 50 на самой ветке.
    assert Decimal(row["total"]) == Decimal("250")
    assert row["path"] == "Groceries"


async def test_path_names_the_whole_branch(client: AsyncClient, categories):
    """Имена категорий не уникальны: «Вода» под «Продуктами» и «Вода» под
    «Коммуналкой» — разные строки, и различить их можно только путём."""
    parent = categories["Groceries"]["id"]
    child = (
        await client.post(
            "/categories",
            json={"name": "Вода", "kind": "expense", "color": "#aabbcc", "parent_id": parent},
        )
    ).json()

    await _watch(client, child["id"])
    watchlist = (await client.get("/plans/watchlist?year=2026")).json()
    assert _row(watchlist, "Вода")["path"] == "Groceries · Вода"


async def test_previous_year_stands_next_to_the_current_one(client: AsyncClient, account_id, categories):
    """Вопрос к списку не «сколько», а «больше или меньше, чем было»."""
    await client.post(
        "/transactions",
        json=txn_payload(
            account_id, amount="1000.00", date="2025-03-10", category_id=categories["Groceries"]["id"]
        ),
    )
    await client.post(
        "/transactions",
        json=txn_payload(
            account_id, amount="1500.00", date="2026-03-10", category_id=categories["Groceries"]["id"]
        ),
    )

    await _watch(client, categories["Groceries"]["id"])
    watchlist = (await client.get("/plans/watchlist?year=2026")).json()
    row = _row(watchlist, "Groceries")
    assert Decimal(row["total"]) == Decimal("1500")
    assert Decimal(row["previous_total"]) == Decimal("1000")


async def test_unwatching_removes_the_row(client: AsyncClient, categories):
    """Список наблюдения на то и список, что из него выходят."""
    await _watch(client, categories["Groceries"]["id"])
    assert len((await client.get("/plans/watchlist?year=2026")).json()["rows"]) == 1

    resp = await client.patch(f"/categories/{categories['Groceries']['id']}", json={"is_watched": False})
    assert resp.status_code == 200, resp.text
    assert (await client.get("/plans/watchlist?year=2026")).json()["rows"] == []
