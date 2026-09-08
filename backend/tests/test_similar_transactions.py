"""Предупреждение о повторном вводе.

Учёт ведут вперемешку: сегодняшнее записывают сразу, вчерашнее и
позавчерашнее — потом. При таком порядке одна покупка легко записывается
дважды и не бросается в глаза, потому что в списке эти строки оказываются
не рядом. Проверяется, что приложение находит такой повтор до записи —
и что оно не находит его там, где повтора нет.
"""
from httpx import AsyncClient

from tests.helpers import txn_payload


async def _similar(client: AsyncClient, **params) -> list[dict]:
    resp = await client.get("/transactions/similar", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_finds_the_same_transaction_on_the_same_day(client: AsyncClient, account_id, categories):
    await client.post(
        "/transactions",
        json=txn_payload(account_id, amount="40.00", description="Автобус", date="2026-03-10"),
    )

    found = await _similar(
        client, date="2026-03-10", type="expense", amount="40.00", description="Автобус"
    )
    assert len(found) == 1
    assert found[0]["description"] == "Автобус"
    # Счёт показывается, чтобы человек увидел, куда записал в прошлый раз.
    assert found[0]["account_name"]


async def test_ignores_another_day(client: AsyncClient, account_id):
    """Ежедневная поездка на автобусе — не повтор. Иначе предупреждение
    срабатывало бы каждый день и его перестали бы читать."""
    await client.post(
        "/transactions",
        json=txn_payload(account_id, amount="40.00", description="Автобус", date="2026-03-10"),
    )

    assert await _similar(
        client, date="2026-03-11", type="expense", amount="40.00", description="Автобус"
    ) == []


async def test_ignores_another_amount(client: AsyncClient, account_id):
    await client.post(
        "/transactions",
        json=txn_payload(account_id, amount="40.00", description="Автобус", date="2026-03-10"),
    )

    assert await _similar(
        client, date="2026-03-10", type="expense", amount="55.00", description="Автобус"
    ) == []


async def test_description_matches_regardless_of_case_and_spaces(client: AsyncClient, account_id):
    """«автобус» и «Автобус  » — одна и та же поездка. Требовать точного
    совпадения значило бы пропускать ровно те повторы, которые вводят
    руками и в разное время."""
    await client.post(
        "/transactions",
        json=txn_payload(account_id, amount="40.00", description="Автобус", date="2026-03-10"),
    )

    found = await _similar(
        client, date="2026-03-10", type="expense", amount="40.00", description="  автобус "
    )
    assert len(found) == 1


async def test_different_categories_still_count_as_a_repeat(
    client: AsyncClient, account_id, categories
):
    """Совпадает день, вид, сумма и описание — этого достаточно. Категория
    в сравнение не входит: при повторном вводе её могли выбрать другую, и
    прятать из-за этого предупреждение значило бы пропускать именно тот
    случай, ради которого оно заводится."""
    await client.post(
        "/transactions",
        json=txn_payload(
            account_id,
            amount="500.00",
            description="Продукты",
            category_id=categories["Groceries"]["id"],
            date="2026-03-10",
        ),
    )

    found = await _similar(
        client, date="2026-03-10", type="expense", amount="500.00", description="Продукты"
    )
    assert len(found) == 1


async def test_empty_description_matches_nothing(client: AsyncClient, account_id):
    """По одним лишь дню и сумме под совпадение попадает слишком много
    чужого, и предупреждение превращается в шум, который перестают
    читать."""
    await client.post(
        "/transactions",
        json=txn_payload(account_id, amount="500.00", description="Продукты", date="2026-03-10"),
    )

    assert await _similar(client, date="2026-03-10", type="expense", amount="500.00", description="") == []


async def test_type_is_part_of_the_match(client: AsyncClient, account_id):
    """Доход и расход на одну сумму в один день — не повтор, а обычная
    пара «получил и потратил»."""
    await client.post(
        "/transactions",
        json=txn_payload(account_id, type="income", amount="1000.00", description="Перевод", date="2026-03-10"),
    )

    assert await _similar(
        client, date="2026-03-10", type="expense", amount="1000.00", description="Перевод"
    ) == []


async def test_writing_is_never_blocked(client: AsyncClient, account_id):
    """Проверка отдельным запросом, а не отказом при записи: две поездки на
    автобусе за день законны, и запретить вторую значило бы заставить
    человека врать приложению."""
    payload = txn_payload(account_id, amount="40.00", description="Автобус", date="2026-03-10")
    assert (await client.post("/transactions", json=payload)).status_code == 201
    assert (await client.post("/transactions", json=payload)).status_code == 201
