"""Full-database backup export/import (services/backup_service.py) — only
the parts this change touched: subcategories (self-referential parent_id)
and tags (many-to-many) surviving a round trip.
"""
from httpx import AsyncClient

from tests.helpers import txn_payload as _txn


async def test_backup_roundtrip_preserves_subcategories_and_tags(client: AsyncClient, account_id, categories):
    parent = await client.post("/categories", json={"name": "Custom Parent", "kind": "expense", "color": "#e34948"})
    parent_id = parent.json()["id"]
    child = await client.post(
        "/categories", json={"name": "Custom Child", "kind": "expense", "color": "#e34948", "parent_id": parent_id}
    )
    child_id = child.json()["id"]

    tag = (await client.post("/tags", json={"name": "Roundtrip"})).json()["id"]
    created = await client.post("/transactions", json=_txn(account_id, category_id=child_id, tag_ids=[tag]))
    txn_id = created.json()["id"]

    export_resp = await client.get("/backup/export")
    assert export_resp.status_code == 200
    payload = export_resp.json()

    import_resp = await client.post("/backup/import", json=payload)
    assert import_resp.status_code == 200, import_resp.text

    refetched_categories = {c["id"]: c for c in (await client.get("/categories")).json()}
    assert refetched_categories[child_id]["parent_id"] == parent_id

    refetched_txn = next(t for t in (await client.get("/transactions")).json()["items"] if t["id"] == txn_id)
    assert [t["id"] for t in refetched_txn["tags"]] == [tag]


async def test_backup_import_rejects_transaction_with_unknown_tag_id(client: AsyncClient, account_id, categories):
    export_resp = await client.get("/backup/export")
    payload = export_resp.json()

    created = await client.post(
        "/transactions", json=_txn(account_id, category_id=categories["Groceries"]["id"], date="2026-01-01")
    )
    payload["transactions"] = (await client.get("/transactions")).json()["items"]
    # Reshape to the backup wire format (flat FKs, not nested account/category
    # objects) and inject a tag_id that doesn't exist in payload["tags"].
    payload["transactions"] = [
        {
            "id": t["id"],
            "account_id": t["account_id"],
            "category_id": t["category_id"],
            "transfer_account_id": t["transfer_account_id"],
            "type": t["type"],
            "amount": t["amount"],
            "description": t["description"],
            "merchant": t["merchant"],
            "date": t["date"],
            "tag_ids": [999999] if t["id"] == created.json()["id"] else [],
        }
        for t in payload["transactions"]
    ]

    resp = await client.post("/backup/import", json=payload)
    assert resp.status_code == 400


async def test_backup_roundtrip_preserves_transaction_splits(client: AsyncClient, account_id, categories):
    groceries = categories["Groceries"]["id"]
    sweets = (
        await client.post("/categories", json={"name": "Sweets", "kind": "expense", "color": "#7a869a", "parent_id": groceries})
    ).json()["id"]
    created = await client.post(
        "/transactions",
        json=_txn(
            account_id,
            amount="100.00",
            category_id=None,
            splits=[
                {"category_id": groceries, "amount": "70.00"},
                {"category_id": sweets, "amount": "30.00", "note": "candy and snacks"},
            ],
        ),
    )
    txn_id = created.json()["id"]

    payload = (await client.get("/backup/export")).json()
    assert len(payload["transaction_splits"]) == 2

    import_resp = await client.post("/backup/import", json=payload)
    assert import_resp.status_code == 200, import_resp.text

    refetched = next(t for t in (await client.get("/transactions")).json()["items"] if t["id"] == txn_id)
    splits_by_note = {s["note"]: s for s in refetched["splits"]}
    assert splits_by_note["candy and snacks"]["category_id"] == sweets
    assert refetched["category"] is None

async def test_a_branch_moved_under_a_newer_category_still_restores(
    client: AsyncClient, account_id, categories
):
    """Копия восстанавливается, даже если ребёнок записан раньше родителя.

    Так и выглядела настоящая поломка. Восстановление раскладывало
    категории на два ведра — сначала корневые, потом все остальные, — и для
    одного уровня вложенности этого хватало. С произвольной вложенностью
    во втором ведре внук оказывается раньше родителя: порядок там по
    номеру, а номер у ребёнка меньше, если ветку перенесли под категорию,
    созданную позже.

    На рабочей установке с её деревом из 177 категорий копия не
    восстанавливалась вовсе: «Key (parent_id)=(7) is not present in table
    categories». Выгрузка при этом работала, и файл выглядел целым —
    заметить можно было только попыткой восстановить.
    """
    root = (await client.post(
        "/categories", json={"name": "Корень", "kind": "expense", "color": "#e34948"}
    )).json()
    first = (await client.post(
        "/categories",
        json={"name": "Переносимая", "kind": "expense", "color": "#e34948", "parent_id": root["id"]},
    )).json()
    second = (await client.post(
        "/categories",
        json={"name": "Новый родитель", "kind": "expense", "color": "#e34948", "parent_id": root["id"]},
    )).json()
    # Ветку переносят под категорию с бо́льшим номером — обычное дело, когда
    # дерево перестраивают по ходу.
    moved = await client.patch(f"/categories/{first['id']}", json={"parent_id": second["id"]})
    assert moved.status_code == 200, moved.text
    assert first["id"] < second["id"]

    payload = (await client.get("/backup/export")).json()
    # Список переворачивается намеренно: порядок в файле — не договор, и
    # восстановление не должно от него зависеть. На рабочей установке
    # ребёнок оказался раньше родителя сам, без всякого перевёртывания.
    payload["categories"].reverse()

    resp = await client.post("/backup/import", json=payload)
    assert resp.status_code == 200, resp.text

    restored = {row["id"]: row for row in (await client.get("/categories")).json()}
    assert restored[first["id"]]["parent_id"] == second["id"]
    assert restored[second["id"]]["parent_id"] == root["id"]


async def test_a_backup_with_a_cycle_is_refused_with_a_reason(
    client: AsyncClient, account_id, categories
):
    """Круг в дереве приложение не создаёт, но файл могли поправить руками.

    Отказ с понятной причиной лучше, чем вечный цикл в обходе или отказ
    самой базы с текстом про внешний ключ.
    """
    payload = (await client.get("/backup/export")).json()
    first, second = payload["categories"][0], payload["categories"][1]
    first["parent_id"] = second["id"]
    second["parent_id"] = first["id"]

    resp = await client.post("/backup/import", json=payload)
    assert resp.status_code == 400, resp.text
    assert "cycle" in resp.json()["detail"].lower()
