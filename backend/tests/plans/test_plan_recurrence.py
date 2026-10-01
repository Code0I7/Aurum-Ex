"""Расписание плана: не только «каждый месяц».

Видов плана было три — разовый, ежемесячный, ежедневный, — и всё, что в них
не укладывалось, человек заводил руками: «раз в квартал» четырьмя разовыми
записями, «каждые две недели» никак.

Сумма означает одно и то же во всех проверках ниже: столько стоит одно
повторение. В месяц попадает столько, сколько повторений в него уложилось,
— поэтому март с тремя подходящими понедельниками дороже февраля с двумя, и
это не ошибка, а то, как выглядят деньги.

Точка отсчёта — начало самого раннего отрезка: без неё «каждые две недели»
не значат ничего.
"""
from decimal import Decimal

from httpx import AsyncClient


async def _category(client: AsyncClient, name: str) -> dict:
    resp = await client.post("/categories", json={"name": name, "kind": "expense", "color": "#557799"})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _plan(client: AsyncClient, category_id: int, amount: str, **rule) -> dict:
    payload = {
        "category_id": category_id,
        "periods": [{"amount": amount, "valid_from": rule.pop("valid_from", "2026-01-01")}],
        **rule,
    }
    resp = await client.post("/plans", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _months(client: AsyncClient, category_id: int, year: int = 2026) -> list[Decimal]:
    overview = (await client.get(f"/plans/overview?year={year}")).json()
    row = next((r for r in overview["rows"] if r["category_id"] == category_id), None)
    # Строки нет, когда план в этом году ничего не обещает и фактов тоже
    # нет: для проверки это то же самое, что двенадцать нулей.
    if row is None:
        return [Decimal("0")] * 12
    return [Decimal(cell["planned"]) for cell in row["months"]]


async def test_every_two_weeks_counts_the_mondays_of_each_month(client: AsyncClient):
    """Тот самый случай, которого раньше не было совсем.

    Отсчёт от понедельника 5 января: январь и февраль дают по два
    попадания, март — три. Третье не лишнее: в марте таких понедельников
    действительно три, и деньги за него человек заплатит.
    """
    category = await _category(client, "Уборка")
    await _plan(
        client,
        category["id"],
        "1000.00",
        kind="week",
        repeat_every=2,
        weekdays=[0],
        valid_from="2026-01-05",
    )

    months = await _months(client, category["id"])
    assert months[0] == Decimal("2000")  # 5 и 19 января
    assert months[1] == Decimal("2000")  # 2 и 16 февраля
    assert months[2] == Decimal("3000")  # 2, 16 и 30 марта


async def test_weekly_takes_every_chosen_day(client: AsyncClient):
    category = await _category(client, "Бассейн")
    await _plan(
        client, category["id"], "500.00", kind="week", weekdays=[0, 3], valid_from="2026-01-01"
    )

    months = await _months(client, category["id"])
    # Январь: четыре понедельника и пять четвергов — девять занятий.
    assert months[0] == Decimal("4500")


async def test_a_quarterly_plan_stands_in_four_months(client: AsyncClient):
    category = await _category(client, "Страховка")
    await _plan(client, category["id"], "9000.00", kind="month", repeat_every=3)

    months = await _months(client, category["id"])
    assert [index + 1 for index, value in enumerate(months) if value] == [1, 4, 7, 10]


async def test_monthly_can_stand_on_two_dates(client: AsyncClient):
    """«Плачу 1-го и 15-го» — два повторения в месяц, а не одно."""
    category = await _category(client, "Аренда")
    await _plan(
        client,
        category["id"],
        "700.00",
        kind="month",
        month_day_mode="day_of_month",
        month_days=[1, 15],
    )

    months = await _months(client, category["id"])
    assert months == [Decimal("1400")] * 12


async def test_the_last_workday_moves_with_the_month(client: AsyncClient):
    """Ради этого пункта и не стали пускать в числа 29–31: «последний
    рабочий» в январе 30-е, в феврале 27-е, и числом это не записать."""
    category = await _category(client, "Зарплата курьеру")
    await _plan(client, category["id"], "3000.00", kind="month", month_day_mode="last_workday")

    months = await _months(client, category["id"])
    # Повторение одно в каждом месяце — меняется только дата внутри него.
    assert months == [Decimal("3000")] * 12


async def test_a_yearly_plan_can_stand_on_the_first_thursday_of_october(client: AsyncClient):
    category = await _category(client, "Техосмотр")
    await _plan(
        client,
        category["id"],
        "4000.00",
        kind="year",
        months=[10],
        month_day_mode="nth_weekday",
        nth_weekday=1,
        weekdays=[3],
    )

    months = await _months(client, category["id"])
    assert months[9] == Decimal("4000")  # 1 октября 2026 — четверг
    assert [value for value in months if value] == [Decimal("4000")]


async def test_a_yearly_plan_skips_the_years_between(client: AsyncClient):
    category = await _category(client, "Загранпаспорт")
    await _plan(client, category["id"], "5000.00", kind="year", repeat_every=2, months=[3])

    assert (await _months(client, category["id"], 2026))[2] == Decimal("5000")
    assert (await _months(client, category["id"], 2027))[2] == Decimal("0")
    assert (await _months(client, category["id"], 2028))[2] == Decimal("5000")


async def test_every_other_day_can_skip_the_weekends(client: AsyncClient):
    category = await _category(client, "Бег")
    await _plan(
        client, category["id"], "100.00", kind="day", repeat_every=2, skip_weekends=True
    )

    months = await _months(client, category["id"])
    assert months[0] == Decimal("1100")  # 11 попаданий в январе
    assert months[1] == Decimal("1000")  # 10 в феврале


async def test_the_step_has_a_ceiling(client: AsyncClient):
    """Потолок взят с запасом и стоит на всех частотах одинаково: «каждые
    36 месяцев» осмысленно, «каждые 400» — опечатка."""
    category = await _category(client, "Ерунда")
    resp = await client.post(
        "/plans",
        json={
            "category_id": category["id"],
            "kind": "month",
            "repeat_every": 400,
            "periods": [{"amount": "100.00", "valid_from": "2026-01-01"}],
        },
    )
    assert resp.status_code == 422, resp.text


async def test_a_day_of_month_beyond_the_28th_is_refused(client: AsyncClient):
    """31 февраля не существует, и решать за человека, что он имел в виду,
    приложение не станет: для конца месяца есть отдельные пункты."""
    category = await _category(client, "Ерунда 2")
    resp = await client.post(
        "/plans",
        json={
            "category_id": category["id"],
            "kind": "month",
            "month_day_mode": "day_of_month",
            "month_days": [31],
            "periods": [{"amount": "100.00", "valid_from": "2026-01-01"}],
        },
    )
    assert resp.status_code == 422, resp.text


async def test_settings_that_mean_nothing_here_are_refused(client: AsyncClient):
    """Молча игнорировать их нельзя: человек, выбравший понедельник, ждал
    понедельника, и тихо посчитанный по-другому план он заметит через год."""
    category = await _category(client, "Ерунда 3")
    resp = await client.post(
        "/plans",
        json={
            "category_id": category["id"],
            "kind": "month",
            "weekdays": [0],
            "periods": [{"amount": "100.00", "valid_from": "2026-01-01"}],
        },
    )
    assert resp.status_code == 422, resp.text


async def test_a_monthly_plan_without_a_day_keeps_its_old_behaviour(client: AsyncClient):
    """Планы, заведённые до расписания, обязаны считаться как считались."""
    category = await _category(client, "Связь")
    await _plan(client, category["id"], "700.00", kind="month")

    assert await _months(client, category["id"]) == [Decimal("700")] * 12
