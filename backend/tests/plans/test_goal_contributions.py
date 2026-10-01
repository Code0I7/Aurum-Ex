"""История накопления: чтение, правка и удаление взносов.

Взнос — отметка «столько отложено», а не движение денег. До сих пор его
можно было только создать: ошибся на нуле — и единственным способом
починить оставался обратный взнос. «Накоплено» сходилось, а в истории
оставались две строки, которых не было.
"""
from decimal import Decimal

from httpx import AsyncClient


async def _goal(client: AsyncClient) -> dict:
    resp = await client.post("/goals", json={"name": "Ноутбук", "target_amount": "50000"})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _contribute(client: AsyncClient, goal_id: int, amount: str, on: str) -> dict:
    resp = await client.post(
        f"/goals/{goal_id}/contributions", json={"amount": amount, "date": on}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _history(client: AsyncClient, goal_id: int) -> list[dict]:
    resp = await client.get(f"/goals/{goal_id}/contributions")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_the_history_adds_up_step_by_step(client: AsyncClient):
    """Лесенка «накоплено» считается на сервере: правило «по дате, а при
    равных датах по порядку ввода» должно быть одно."""
    goal = await _goal(client)
    await _contribute(client, goal["id"], "1000", "2026-01-10")
    await _contribute(client, goal["id"], "2500", "2026-02-01")
    # Вынос: ступенька вниз, а не отдельная сущность.
    await _contribute(client, goal["id"], "-500", "2026-02-15")

    history = await _history(client, goal["id"])

    assert [Decimal(row["running_total"]) for row in history] == [
        Decimal("1000"),
        Decimal("3500"),
        Decimal("3000"),
    ]


async def test_the_history_is_ordered_by_date_not_by_entry(client: AsyncClient):
    """Взнос, записанный задним числом, встаёт на своё место."""
    goal = await _goal(client)
    await _contribute(client, goal["id"], "1000", "2026-03-01")
    await _contribute(client, goal["id"], "700", "2026-01-15")

    history = await _history(client, goal["id"])

    assert [row["date"] for row in history] == ["2026-01-15", "2026-03-01"]
    assert Decimal(history[-1]["running_total"]) == Decimal("1700")


async def test_a_mistyped_contribution_can_be_corrected(client: AsyncClient):
    """Ради этого всё и делалось: ошибка на нуле правится, а не
    компенсируется обратным взносом."""
    goal = await _goal(client)
    await _contribute(client, goal["id"], "10000", "2026-01-10")
    wrong = (await _history(client, goal["id"]))[0]

    resp = await client.patch(
        f"/goals/{goal['id']}/contributions/{wrong['id']}", json={"amount": "1000"}
    )
    assert resp.status_code == 200, resp.text
    # Ответ — сама цель: «накоплено» под названием обязано обновиться сразу.
    assert Decimal(resp.json()["current_amount"]) == Decimal("1000")

    history = await _history(client, goal["id"])
    assert len(history) == 1
    assert Decimal(history[0]["amount"]) == Decimal("1000")


async def test_a_contribution_can_be_removed_entirely(client: AsyncClient):
    goal = await _goal(client)
    await _contribute(client, goal["id"], "1000", "2026-01-10")
    await _contribute(client, goal["id"], "2000", "2026-02-10")
    extra = (await _history(client, goal["id"]))[1]

    resp = await client.delete(f"/goals/{goal['id']}/contributions/{extra['id']}")
    assert resp.status_code == 200, resp.text
    assert Decimal(resp.json()["current_amount"]) == Decimal("1000")

    assert len(await _history(client, goal["id"])) == 1


async def test_a_zero_correction_is_refused(client: AsyncClient):
    """Ноль — не сумма, а способ оставить в истории строку ни о чём."""
    goal = await _goal(client)
    await _contribute(client, goal["id"], "1000", "2026-01-10")
    row = (await _history(client, goal["id"]))[0]

    resp = await client.patch(
        f"/goals/{goal['id']}/contributions/{row['id']}", json={"amount": "0"}
    )
    assert resp.status_code == 422, resp.text


async def test_a_contribution_of_another_goal_is_not_reachable(client: AsyncClient):
    """Адрес правки собирается из двух номеров, и без проверки чужой взнос
    правился бы через свою цель."""
    mine = await _goal(client)
    other = await _goal(client)
    await _contribute(client, other["id"], "1000", "2026-01-10")
    stranger = (await _history(client, other["id"]))[0]

    resp = await client.patch(
        f"/goals/{mine['id']}/contributions/{stranger['id']}", json={"amount": "5"}
    )
    assert resp.status_code == 404, resp.text


async def test_the_history_of_a_missing_goal_is_not_an_empty_list(client: AsyncClient):
    """Пустой список означал бы «цель есть, взносов нет» — а цели нет."""
    assert (await client.get("/goals/9999/contributions")).status_code == 404
