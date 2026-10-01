"""Питомец как участник операции.

Питомец — отдельное измерение, а не ветка категорий: корм коту это
одновременно «Питомцы → Корм» и «для Мурзика». Вплести кличку в дерево
значило бы дублировать всю ветку на каждое животное — ровно так исходная
таблица дошла до полутора сотен подкатегорий.

В API вид участника был с самого начала, но в интерфейсе его выставить было
нечем: форма справочника отправляла одно имя, и всё заводилось человеком.
Тесты закрывают путь, который теперь открыт из интерфейса.
"""
from httpx import AsyncClient


async def test_a_pet_can_be_created(client: AsyncClient):
    resp = await client.post("/participants", json={"name": "Мурзик", "kind": "pet"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["kind"] == "pet"


async def test_a_participant_is_a_person_by_default(client: AsyncClient):
    """Умолчание важно: людей заводят часто, питомцев — раз в несколько лет."""
    resp = await client.post("/participants", json={"name": "Иван"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["kind"] == "person"


async def test_the_kind_can_be_switched_later(client: AsyncClient):
    """Щелчок по значку в справочнике — это PATCH одного поля."""
    created = (await client.post("/participants", json={"name": "Барсик"})).json()
    resp = await client.patch(f"/participants/{created['id']}", json={"kind": "pet"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["kind"] == "pet"

    resp = await client.patch(f"/participants/{created['id']}", json={"kind": "person"})
    assert resp.json()["kind"] == "person"


async def test_renaming_does_not_reset_the_kind(client: AsyncClient):
    """Правка имени идёт тем же PATCH, что и вид. Если бы схема не была
    частичной, переименование сбрасывало бы питомца в человека."""
    created = (await client.post("/participants", json={"name": "Мурзик", "kind": "pet"})).json()
    resp = await client.patch(f"/participants/{created['id']}", json={"name": "Мурзик Второй"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Мурзик Второй"
    assert resp.json()["kind"] == "pet"


async def test_spending_can_be_attributed_to_a_pet(client: AsyncClient, account_id: int):
    """Собственно то, ради чего вид заведён: корм записан на животное, а
    категория осталась общей."""
    pet = (await client.post("/participants", json={"name": "Мурзик", "kind": "pet"})).json()
    category = (await client.post(
        "/categories", json={"name": "Корм", "kind": "expense", "color": "#557799"}
    )).json()

    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "540.00",
            "description": "Корм",
            "date": "2026-03-05",
            "category_id": category["id"],
            "participant_id": pet["id"],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["participant_id"] == pet["id"]


async def test_two_pets_share_one_category(client: AsyncClient, account_id: int):
    """Второй питомец стоит одну строку справочника, а не копию ветки —
    это и есть причина, по которой вид не живёт в категориях."""
    murzik = (await client.post("/participants", json={"name": "Мурзик", "kind": "pet"})).json()
    barsik = (await client.post("/participants", json={"name": "Барсик", "kind": "pet"})).json()
    category = (await client.post(
        "/categories", json={"name": "Корм", "kind": "expense", "color": "#557799"}
    )).json()

    for pet, amount in ((murzik, "540.00"), (barsik, "610.00")):
        resp = await client.post(
            "/transactions",
            json={
                "account_id": account_id,
                "type": "expense",
                "amount": amount,
                "description": "Корм",
                "date": "2026-03-05",
                "category_id": category["id"],
                "participant_id": pet["id"],
            },
        )
        assert resp.status_code == 201, resp.text

    categories = (await client.get("/categories")).json()
    assert len([row for row in categories if row["name"] == "Корм"]) == 1

    for pet, count in ((murzik, 1), (barsik, 1)):
        page = (await client.get(f"/transactions?participant_id={pet['id']}")).json()
        assert page["total"] == count
