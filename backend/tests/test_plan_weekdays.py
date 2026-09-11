"""План по будням календаря.

У ежедневного плана было два режима: календарные дни и отработанные дни из
work_periods. Второй требует вводить дни руками — он для вахты и смен, и
ошибка в нём портит план целиком: два дня вместо двадцати дают 400 ₽ там,
где потрачено несколько тысяч.

Пятидневке нужен третий режим: будни календаря. Они известны на годы вперёд
и ничего вводить не требуют.
"""
from datetime import date

from httpx import AsyncClient

from app.services.plan_service import weekdays_in_month


def test_weekdays_are_counted_by_the_calendar():
    # Сентябрь 2026: 30 дней, начинается со вторника — 22 будних дня.
    assert weekdays_in_month(2026, 9) == 22
    # Февраль 2026: 28 дней, начинается с воскресенья — 20 будних.
    assert weekdays_in_month(2026, 2) == 20
    # Май 2026: 31 день, начинается с пятницы — 21 будний.
    assert weekdays_in_month(2026, 5) == 21


def test_weekdays_never_exceed_calendar_days():
    """Защита от смещения в подсчёте дня недели: будней не бывает больше,
    чем дней, и меньше, чем дней минус десять."""
    for year in (2024, 2025, 2026, 2027):
        for month in range(1, 13):
            weekdays = weekdays_in_month(year, month)
            total = (date(year + (month == 12), month % 12 + 1, 1) - date(year, month, 1)).days
            assert 0 < weekdays <= total
            assert total - weekdays <= 10


async def _category(client: AsyncClient, name: str = "Столовая") -> dict:
    resp = await client.post("/categories", json={"name": name, "kind": "expense", "color": "#557799"})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_a_weekday_plan_multiplies_by_weekdays(client: AsyncClient):
    category = await _category(client)
    resp = await client.post(
        "/plans",
        json={
            "category_id": category["id"],
            "kind": "daily",
            "amount": "200.00",
            "valid_from": "2026-01-01",
            "weekdays_only": True,
        },
    )
    assert resp.status_code == 201, resp.text

    overview = (await client.get("/plans/overview?year=2026")).json()
    row = next(r for r in overview["rows"] if r["category_id"] == category["id"])
    # Сентябрь — девятый месяц, 22 будних дня по 200 ₽.
    assert row["months"][8]["planned"] == "4400.00"


async def test_the_two_day_modes_cannot_be_combined(client: AsyncClient):
    """Отработанные дни и будни отвечают на разные вопросы: первое — факт,
    второе — календарь. Вместе они означали бы два числа дней на месяц."""
    category = await _category(client)
    resp = await client.post(
        "/plans",
        json={
            "category_id": category["id"],
            "kind": "daily",
            "amount": "200.00",
            "valid_from": "2026-01-01",
            "workdays_only": True,
            "weekdays_only": True,
        },
    )
    assert resp.status_code == 422, resp.text


async def test_weekdays_only_is_for_daily_plans(client: AsyncClient):
    category = await _category(client)
    resp = await client.post(
        "/plans",
        json={
            "category_id": category["id"],
            "kind": "monthly",
            "amount": "700.00",
            "valid_from": "2026-01-01",
            "weekdays_only": True,
        },
    )
    assert resp.status_code == 422, resp.text


async def test_a_plain_daily_plan_still_uses_calendar_days(client: AsyncClient):
    """Без обеих галочек поведение прежнее."""
    category = await _category(client, "Вода")
    resp = await client.post(
        "/plans",
        json={
            "category_id": category["id"],
            "kind": "daily",
            "amount": "50.00",
            "valid_from": "2026-01-01",
        },
    )
    assert resp.status_code == 201, resp.text

    overview = (await client.get("/plans/overview?year=2026")).json()
    row = next(r for r in overview["rows"] if r["category_id"] == category["id"])
    # Сентябрь — 30 календарных дней.
    assert row["months"][8]["planned"] == "1500.00"
