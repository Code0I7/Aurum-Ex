"""Длина рабочего дня считается по данным, а не восьмёркой в коде.

Цена покупки «в днях» делилась на восемь часов. У человека с днём в 10,5
часа покупка на 33 624 ₽ показывалась как 34 дня вместо 25,9 — завышение на
треть ровно на том числе, которое существует ради точного ощущения. У
человека с днём 5,5 ошибка шла в другую сторону.

Приложение знает настоящую длину: в записи месяца лежат и часы, и рабочие
дни. Берётся она тем же скользящим окном в три месяца, что и ставка: у
вопроса «сколько я получаю за час» и вопроса «сколько это в днях» один и тот
же срок.
"""
from decimal import Decimal

from httpx import AsyncClient


async def _work(client: AsyncClient, year: int, month: int, hours: str, workdays: int) -> None:
    resp = await client.put(
        "/work-periods",
        json={"year": year, "month": month, "hours": hours, "workdays": workdays},
    )
    assert resp.status_code in (200, 201), resp.text


async def _rates(client: AsyncClient) -> dict:
    resp = await client.get("/work-periods/hourly-rates")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_the_day_is_hours_divided_by_workdays(client: AsyncClient):
    """Десять с половиной часов в день — потому что так записано."""
    await _work(client, 2025, 1, "241.50", 23)
    await _work(client, 2025, 2, "210.00", 20)
    await _work(client, 2025, 3, "220.50", 21)

    day_hours = (await _rates(client))["day_hours"]
    assert Decimal(day_hours["months"]["2025-03"]) == Decimal("10.50")


async def test_the_day_uses_the_same_three_month_window_as_the_rate(client: AsyncClient):
    """Окно общее, и короткий месяц в одиночку длину дня не переписывает."""
    await _work(client, 2025, 1, "160.00", 20)  # по 8
    await _work(client, 2025, 2, "160.00", 20)  # по 8
    await _work(client, 2025, 3, "40.00", 20)  # по 2 — выбивается

    day_hours = (await _rates(client))["day_hours"]
    # Окно марта: 160 + 160 + 40 часов на 60 дней — шесть, а не два.
    assert Decimal(day_hours["months"]["2025-03"]) == Decimal("6.00")


async def test_each_period_keeps_its_own_day(client: AsyncClient):
    """Покупка 2022 года переводится в дни по дню 2022 года.

    Иначе выходит, что при переходе на долгие смены подешевели и прошлые
    покупки, — а они стоили столько рабочих дней, сколько стоили.
    """
    for month in (1, 2, 3):
        await _work(client, 2022, month, "110.00", 20)  # по 5,5
    for month in (1, 2, 3):
        await _work(client, 2025, month, "210.00", 20)  # по 10,5

    day_hours = (await _rates(client))["day_hours"]
    assert Decimal(day_hours["months"]["2022-03"]) == Decimal("5.50")
    assert Decimal(day_hours["months"]["2025-03"]) == Decimal("10.50")


async def test_the_average_day_covers_months_without_their_own(client: AsyncClient):
    """Месяц, для которого длины нет, падает на среднюю за всё время —
    та же лестница, что у ставки."""
    await _work(client, 2025, 1, "200.00", 20)
    await _work(client, 2025, 2, "200.00", 20)

    day_hours = (await _rates(client))["day_hours"]
    assert Decimal(day_hours["overall"]) == Decimal("10.00")


async def test_a_month_without_workdays_does_not_claim_a_day_length(client: AsyncClient):
    """Часы без дней длину дня не дают: делить не на что.

    Ноль рабочих дней — это не день нулевой длины, а отсутствие сведений, и
    выдумывать из него число нельзя.
    """
    await _work(client, 2025, 5, "100.00", 0)

    day_hours = (await _rates(client))["day_hours"]
    assert "2025-05" not in day_hours["months"]
    assert day_hours["overall"] is None


async def test_no_work_periods_at_all_means_no_day_length(client: AsyncClient):
    """На пустой установке длины нет вовсе — интерфейс возьмёт
    восьмичасовой день, но уже как последнее средство, а не молча."""
    day_hours = (await _rates(client))["day_hours"]
    assert day_hours == {"months": {}, "overall": None}


async def test_the_day_ignores_how_much_of_the_month_has_passed(client: AsyncClient):
    """Длина дня не зависит от того, сколько месяца прошло.

    Ставка делит доход на уже отработанную долю часов — иначе первого числа
    выходит, что человек заработал два рубля в час. А длина дня — отношение,
    и доля сократилась бы в нём сама; применять её значило бы делать лишнюю
    работу с риском ошибиться в одной из двух половин.
    """
    from datetime import date

    today = date.today()
    await _work(client, today.year, today.month, "210.00", 20)

    day_hours = (await _rates(client))["day_hours"]
    key = f"{today.year:04d}-{today.month:02d}"
    assert Decimal(day_hours["months"][key]) == Decimal("10.50")
