"""Список операций фильтруется веткой, а не одной категорией.

Отчёт состоит из трёх блоков поверх одних и тех же денег: рейтинг статей,
график по месяцам и список операций под ними. Первые два сворачивают
подкатегории — так задумано, ветка и есть статья расхода. Список этого не
делал и показывал только то, что записано прямо в выбранную категорию.

Со стороны это выглядело как поломанный диапазон дат: график за год, под
ним одна операция: ветка с итогом в сотни тысяч раскрывалась строкой на
триста рублей, а остальное лежало в её подкатегориях.
"""
from httpx import AsyncClient


async def _category(client: AsyncClient, name: str, parent_id: int | None = None) -> dict:
    resp = await client.post(
        "/categories",
        json={"name": name, "kind": "expense", "color": "#557799", "parent_id": parent_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _spend(client: AsyncClient, account_id: int, category_id: int, amount: str) -> int:
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
    return resp.json()["id"]


async def test_branch_filter_reaches_the_whole_subtree(client: AsyncClient, account_id: int):
    """Фильтр по корню показывает и то, что записано во внуках."""
    people = await _category(client, "Люди")
    gifts = await _category(client, "Подарки", people["id"])
    birthdays = await _category(client, "Дни рождения", gifts["id"])

    await _spend(client, account_id, people["id"], "369.32")
    await _spend(client, account_id, gifts["id"], "1500.00")
    await _spend(client, account_id, birthdays["id"], "2000.00")

    page = (await client.get(f"/transactions?category_id={people['id']}")).json()
    assert page["total"] == 3

    # А снизу вверх ветка не расширяется: у «Подарков» своя пара, «Люди» в
    # неё не входят.
    page = (await client.get(f"/transactions?category_id={gifts['id']}")).json()
    assert page["total"] == 2


async def test_branch_filter_agrees_with_the_report_above_it(client: AsyncClient, account_id: int):
    """Число операций в списке и сумма в графике считаются по одной ветке.

    Это и есть смысл правки: три блока отчёта обязаны говорить об одних и
    тех же деньгах.
    """
    food = await _category(client, "Еда")
    groceries = await _category(client, "Продукты", food["id"])
    await _spend(client, account_id, groceries["id"], "700.00")
    await _spend(client, account_id, groceries["id"], "300.00")

    report = (await client.get(f"/reports/category-spending?category_id={food['id']}")).json()
    page = (await client.get(f"/transactions?category_id={food['id']}")).json()

    assert page["total"] == 2
    assert report["transaction_count"] == 2
    assert report["total_amount"] == "1000.00"


async def test_a_leaf_filter_stays_exact(client: AsyncClient, account_id: int):
    """У категории без детей поведение прежнее — ветка это она сама."""
    taxi = await _category(client, "Такси")
    bus = await _category(client, "Автобус")
    await _spend(client, account_id, taxi["id"], "250.00")
    await _spend(client, account_id, bus["id"], "28.00")

    page = (await client.get(f"/transactions?category_id={taxi['id']}")).json()
    assert page["total"] == 1
    assert page["items"][0]["amount"] == "250.00"


async def test_split_lines_are_found_through_the_branch(client: AsyncClient, account_id: int):
    """Сплит на подкатегорию попадает в фильтр по корню.

    У сплит-операции своя категория пуста — она живёт в строках. Ветка
    должна доставать и через них, иначе разложенный чек выпадает из отчёта
    по статье, к которой относится целиком.
    """
    food = await _category(client, "Еда")
    sweets = await _category(client, "Сладости", food["id"])
    bread = await _category(client, "Хлеб", food["id"])

    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "300.00",
            "description": "Магазин",
            "date": "2026-03-05",
            "splits": [
                {"category_id": sweets["id"], "amount": "180.00"},
                {"category_id": bread["id"], "amount": "120.00"},
            ],
        },
    )
    assert resp.status_code == 201, resp.text

    page = (await client.get(f"/transactions?category_id={food['id']}")).json()
    # Одна операция, а не две: сплит-строки принадлежат одному чеку.
    assert page["total"] == 1
