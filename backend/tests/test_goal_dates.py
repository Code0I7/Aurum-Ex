"""Три даты цели и три числа, которые из них получаются.

Дата у цели была одна и подписана просто «Дата». Показывалась она с
предлогом «до» — как срок, — а заполняли её началом накопления. Теперь
это три разных вопроса и три разных поля:

* когда начали копить;
* к какому числу хотелось бы собрать — обещание себе, ни к чему не
  обязывающее;
* когда собрали на самом деле. Приложение ставит его в момент «Цель
  достигнута», но знает оно день, когда нажали кнопку, а не день, когда
  деньги собрались, — поэтому дата правится руками.
"""
from datetime import date, timedelta

from httpx import AsyncClient


async def _goal(client: AsyncClient, **fields) -> dict:
    payload = {"name": "Ноутбук", "target_amount": "50000"}
    payload.update(fields)
    resp = await client.post("/goals", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _reread(client: AsyncClient, goal_id: int) -> dict:
    listing = (await client.get("/goals")).json()
    return next(row for row in listing if row["id"] == goal_id)


async def test_a_goal_keeps_all_three_dates(client: AsyncClient):
    goal = await _goal(client, started_on="2026-01-10", planned_on="2026-06-01")

    assert goal["started_on"] == "2026-01-10"
    assert goal["planned_on"] == "2026-06-01"
    # Фактической ещё нет: цель копится.
    assert goal["closed_at"] is None


async def test_an_active_goal_counts_from_the_start_to_today(client: AsyncClient):
    """«Копим сорок дней» — про сейчас, и считается до сегодня."""
    started = date.today() - timedelta(days=40)
    goal = await _goal(client, started_on=started.isoformat())

    assert goal["days_saving"] == 40


async def test_the_plan_counts_down_and_then_goes_negative(client: AsyncClient):
    """Просрочка — не ошибка, а обычная жизнь накопления, и говорится о ней
    тем же числом со знаком минус."""
    ahead = await _goal(client, planned_on=(date.today() + timedelta(days=12)).isoformat())
    assert ahead["days_to_plan"] == 12

    behind = await _goal(client, planned_on=(date.today() - timedelta(days=5)).isoformat())
    assert behind["days_to_plan"] == -5


async def test_finishing_a_goal_stops_the_clock(client: AsyncClient):
    """Иначе «копим 40 дней» продолжало бы расти у цели, закрытой год
    назад."""
    started = date.today() - timedelta(days=40)
    goal = await _goal(client, started_on=started.isoformat())

    resp = await client.patch(f"/goals/{goal['id']}", json={"status": "achieved"})
    assert resp.status_code == 200, resp.text

    done = await _reread(client, goal["id"])
    assert done["closed_at"] == date.today().isoformat()
    # Собрали ровно за те же сорок дней, и дальше это число не растёт.
    assert done["days_taken"] == 40
    assert done["days_saving"] == 40


async def test_the_plan_stops_mattering_once_the_goal_is_done(client: AsyncClient):
    """«Просрочено на 300 дней» у выполненной цели — упрёк за то, чего
    давно нет."""
    goal = await _goal(client, planned_on=(date.today() - timedelta(days=300)).isoformat())
    await client.patch(f"/goals/{goal['id']}", json={"status": "achieved"})

    assert (await _reread(client, goal["id"]))["days_to_plan"] is None


async def test_the_actual_date_can_be_corrected_by_hand(client: AsyncClient):
    """Собрал в июне, отметил в августе: приложение знает только второе, и
    метрика «за сколько собрал» иначе врёт на два месяца."""
    goal = await _goal(client, started_on="2026-01-10")
    await client.patch(f"/goals/{goal['id']}", json={"status": "achieved"})

    resp = await client.patch(f"/goals/{goal['id']}", json={"closed_at": "2026-03-01"})
    assert resp.status_code == 200, resp.text

    done = await _reread(client, goal["id"])
    assert done["closed_at"] == "2026-03-01"
    assert done["days_taken"] == 50


async def test_a_cancelled_goal_has_no_collection_time(client: AsyncClient):
    """У отменённой сбора не было — был отказ."""
    goal = await _goal(client, started_on=(date.today() - timedelta(days=10)).isoformat())
    await client.patch(f"/goals/{goal['id']}", json={"status": "cancelled"})

    cancelled = await _reread(client, goal["id"])
    assert cancelled["closed_at"] is not None
    assert cancelled["days_taken"] is None
    # А вот сколько копили до отказа — число осмысленное.
    assert cancelled["days_saving"] == 10


async def test_reopening_a_goal_drops_the_finish_date(client: AsyncClient):
    """Цель, открытая заново, не должна остаться с датой конца, которого
    не было."""
    goal = await _goal(client, started_on="2026-01-10")
    await client.patch(f"/goals/{goal['id']}", json={"status": "achieved"})

    await client.patch(f"/goals/{goal['id']}", json={"status": "active"})

    again = await _reread(client, goal["id"])
    assert again["closed_at"] is None
    assert again["days_taken"] is None


async def test_a_goal_without_dates_says_nothing_instead_of_zero(client: AsyncClient):
    """Ноль здесь означал бы «собрали за день», а это не то же самое, что
    «не знаем, когда начали»."""
    goal = await _goal(client)

    assert goal["days_saving"] is None
    assert goal["days_to_plan"] is None
    assert goal["days_taken"] is None
