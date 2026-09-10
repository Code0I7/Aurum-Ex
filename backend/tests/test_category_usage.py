"""Сколько зацепит удаление категории.

Вопрос перед удалением был правдивым, но безразмерным: «её транзакции
останутся без категории» показывалось одинаково и для пустой категории, и
для той, в которой лежит год истории. Решение принималось вслепую.

Про подкатегории он молчал совсем, а внешний ключ parent_id стоит
ON DELETE SET NULL: дети удалённого родителя не удаляются, а всплывают в
корень отдельными ветками верхнего уровня.
"""
from httpx import AsyncClient


async def _category(client: AsyncClient, name: str, parent_id: int | None = None) -> dict:
    resp = await client.post(
        "/categories",
        json={"name": name, "kind": "expense", "color": "#557799", "parent_id": parent_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _spend(client: AsyncClient, account_id: int, category_id: int, amount: str = "100.00") -> None:
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": amount,
            "description": "Покупка",
            "date": "2026-03-05",
            "category_id": category_id,
        },
    )
    assert resp.status_code == 201, resp.text


async def test_an_untouched_category_reports_zeroes(client: AsyncClient):
    fresh = await _category(client, "Ничего не было")
    usage = (await client.get(f"/categories/{fresh['id']}/usage")).json()
    assert usage == {
        "transactions": 0,
        "items": 0,
        "children": 0,
        "descendants": 0,
        "descendant_transactions": 0,
    }


async def test_own_transactions_are_counted(client: AsyncClient, account_id: int):
    taxi = await _category(client, "Такси")
    await _spend(client, account_id, taxi["id"])
    await _spend(client, account_id, taxi["id"])
    usage = (await client.get(f"/categories/{taxi['id']}/usage")).json()
    assert usage["transactions"] == 2


async def test_a_split_transaction_counts_once(client: AsyncClient, account_id: int):
    """Две строки сплита на одну категорию — это одна операция.

    Без distinct число в вопросе оказалось бы больше, чем на самом деле, а
    завышенное предупреждение перестают читать так же быстро, как пустое.
    """
    sweets = await _category(client, "Сладости")
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "300.00",
            "description": "Магазин",
            "date": "2026-03-05",
            "splits": [
                {"category_id": sweets["id"], "amount": "180.00", "note": "торт"},
                {"category_id": sweets["id"], "amount": "120.00", "note": "печенье"},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    usage = (await client.get(f"/categories/{sweets['id']}/usage")).json()
    assert usage["transactions"] == 1


async def test_the_branch_below_is_reported_separately(client: AsyncClient, account_id: int):
    """Своё и веткино не смешиваются: операции подкатегорий удаление
    переживут, а собственные — нет."""
    people = await _category(client, "Люди")
    gifts = await _category(client, "Подарки", people["id"])
    birthdays = await _category(client, "Дни рождения", gifts["id"])

    await _spend(client, account_id, people["id"])
    await _spend(client, account_id, gifts["id"])
    await _spend(client, account_id, birthdays["id"])

    usage = (await client.get(f"/categories/{people['id']}/usage")).json()
    assert usage["transactions"] == 1
    assert usage["children"] == 1
    assert usage["descendants"] == 2
    assert usage["descendant_transactions"] == 2


async def test_receipt_lines_are_counted(client: AsyncClient, account_id: int):
    """Позиция теряет категорию так же молча, как операция."""
    sweets = await _category(client, "Сладости")
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "300.00",
            "description": "Магазин",
            "date": "2026-03-05",
            "items": [
                {"name": "Торт", "amount": "180.00", "category_id": sweets["id"]},
                {"name": "Печенье", "amount": "120.00", "category_id": sweets["id"]},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    usage = (await client.get(f"/categories/{sweets['id']}/usage")).json()
    assert usage["items"] == 2


async def test_children_really_do_float_up(client: AsyncClient):
    """Проверка самого предупреждения: ребёнок переживает родителя и
    становится веткой верхнего уровня."""
    people = await _category(client, "Люди")
    gifts = await _category(client, "Подарки", people["id"])

    assert (await client.delete(f"/categories/{people['id']}")).status_code == 204

    survivor = next(
        row for row in (await client.get("/categories")).json() if row["id"] == gifts["id"]
    )
    assert survivor["parent_id"] is None


async def test_a_missing_category_is_404(client: AsyncClient):
    assert (await client.get("/categories/999999/usage")).status_code == 404
