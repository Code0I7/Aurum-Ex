"""Операция без описания не должна ронять ни один экран.

Эта ошибка случалась трижды подряд, каждый раз в новом месте: сначала
список операций падал на нулевой сумме, потом обзор — на крупнейшей трате
без описания, потом предупреждение о повторах. Причина всегда одна и та
же: схема показа объявлена строже, чем колонка в базе, и одна строка
обрывает целый экран.

Поэтому проверка не про одно поле, а про все ответы разом: заводим
операцию без описания и обходим каждый экран, где она может всплыть. Новый
экран, забывший про пустое описание, свалится здесь, а не у человека.
"""
from httpx import AsyncClient

from tests.helpers import txn_payload

# (описание проверки, путь). Пути перечислены руками намеренно: это список
# того, где операция показывается, и он должен пополняться вместе с новыми
# экранами.
SCREENS = [
    ("список операций", "/transactions?year=2026&month=5"),
    ("обзор за месяц", "/dashboard/summary?year=2026&month=5&range=month"),
    ("обзор за год", "/dashboard/summary?year=2026&month=5&range=year"),
    ("обзор за всё время", "/dashboard/summary?year=2026&month=5&range=all"),
    ("движение денег", "/cash-flow"),
    ("отчёт по категориям", "/reports/category-ranking"),
    ("капитал", "/net-worth/summary?range=all"),
    ("советы", "/advice"),
    ("оповещения", "/insights/alerts"),
    ("резервная копия", "/backup/export"),
]


async def test_no_screen_breaks_on_a_transaction_without_description(
    client: AsyncClient, account_id, categories
):
    payload = txn_payload(
        account_id,
        amount="1500.00",
        date="2026-05-14",
        category_id=categories["Groceries"]["id"],
    )
    payload.pop("description")
    created = await client.post("/transactions", json=payload)
    assert created.status_code == 201, created.text

    broken = []
    for name, path in SCREENS:
        resp = await client.get(path)
        if resp.status_code != 200:
            broken.append(f"{name} ({path}): {resp.status_code}")
    assert not broken, "Экраны падают на операции без описания: " + "; ".join(broken)


async def test_duplicate_check_survives_a_transaction_without_description(
    client: AsyncClient, account_id
):
    """Поиск повторов возвращает саму операцию, и её описание тоже может
    быть пустым."""
    payload = txn_payload(account_id, amount="40.00", date="2026-05-14", description="Автобус")
    assert (await client.post("/transactions", json=payload)).status_code == 201

    resp = await client.get(
        "/transactions/similar",
        params={"date": "2026-05-14", "type": "expense", "amount": "40.00", "description": "Автобус"},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1
