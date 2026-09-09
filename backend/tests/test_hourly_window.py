"""Скользящее окно в три месяца для ставки за час.

Годовое окно ломалось об январь: первого числа оно состояло из одного
неполного дня, и до февраля цифра была бессмысленной. Помесячное окно
ломалось об аванс: доход приходит рывками, и месяц без зарплаты давал
копейки в час, а следующий — сотни.

Три месяца, заканчивающиеся месяцем самой покупки, закрывают оба случая, и
проверяется здесь именно это: рывки сглаживаются, история остаётся честной
(трата 2024 года считается по заработку 2024-го), а перерыв в работе не
обнуляет заработок за предыдущий месяц.
"""
from datetime import date
from decimal import Decimal

from httpx import AsyncClient

from app.services.hourly_service import _shift, elapsed_share
from tests.helpers import txn_payload


async def _work(client: AsyncClient, year: int, month: int, hours: str) -> None:
    resp = await client.put("/work-periods", json={"year": year, "month": month, "hours": hours})
    assert resp.status_code in (200, 201), resp.text


async def _income(client: AsyncClient, account_id: int, amount: str, on: str) -> None:
    payload = txn_payload(account_id, amount=amount, date=on, description="Зарплата")
    payload["type"] = "income"
    resp = await client.post("/transactions", json=payload)
    assert resp.status_code == 201, resp.text


def test_shift_walks_back_across_the_year_boundary():
    """Январь минус два — это ноябрь прошлого года, а не «минус первый»
    месяц того же. На этом шве годовое окно и ломалось."""
    assert _shift((2026, 1), 1) == (2025, 12)
    assert _shift((2026, 1), 2) == (2025, 11)
    assert _shift((2026, 3), 2) == (2026, 1)


def test_finished_month_is_whole_and_future_is_empty():
    assert elapsed_share(2026, 8, today=date(2026, 9, 9)) == Decimal("1")
    assert elapsed_share(2026, 10, today=date(2026, 9, 9)) == Decimal("0")
    # Сентябрь тридцатидневный: девятого прошло девять дней из тридцати.
    assert elapsed_share(2026, 9, today=date(2026, 9, 9)) == Decimal("9") / Decimal("30")


async def test_a_month_without_pay_borrows_from_its_neighbours(client: AsyncClient, account_id):
    """Ровно то, из-за чего помесячная ставка была шумом: в феврале часы
    отработаны, а деньги пришли в январе и марте. Одномесячное окно дало бы
    ноль, окно в три месяца — настоящую ставку."""
    for month in (1, 2, 3):
        await _work(client, 2024, month, "160")
    await _income(client, account_id, "96000", "2024-01-25")
    await _income(client, account_id, "96000", "2024-03-25")

    months = (await client.get("/work-periods/hourly-rates")).json()["months"]
    # 192 000 ₽ на 480 часов окна января–марта.
    assert Decimal(months["2024-03"]) == Decimal("400.00")


async def test_the_window_ends_at_the_month_asked_about(client: AsyncClient, account_id):
    """История остаётся честной: покупка 2024 года не должна считаться по
    сегодняшнему заработку. Заработок вырос вдвое — ставка старого месяца
    осталась прежней."""
    for month in (1, 2, 3):
        await _work(client, 2024, month, "100")
        await _income(client, account_id, "20000", f"2024-{month:02d}-20")
    for month in (5, 6, 7):
        await _work(client, 2024, month, "100")
        await _income(client, account_id, "40000", f"2024-{month:02d}-20")

    months = (await client.get("/work-periods/hourly-rates")).json()["months"]
    assert Decimal(months["2024-03"]) == Decimal("200.00")
    assert Decimal(months["2024-07"]) == Decimal("400.00")


async def test_a_month_off_does_not_erase_the_month_worked(client: AsyncClient, account_id):
    """Вахта: отработали в марте, деньги пришли в апреле, когда человек уже
    отдыхал. Выкинуть доход месяца без часов значило бы обнулить заработок
    за март."""
    await _work(client, 2024, 3, "200")
    await _income(client, account_id, "100000", "2024-04-10")

    months = (await client.get("/work-periods/hourly-rates")).json()["months"]
    assert Decimal(months["2024-04"]) == Decimal("500.00")


async def test_no_hours_at_all_means_no_rate(client: AsyncClient, account_id):
    """Выдумывать ставку хуже, чем промолчать: без часов стоимость в
    рабочем времени не показывается вовсе."""
    await _income(client, account_id, "50000", "2024-04-10")
    body = (await client.get("/work-periods/hourly-rates")).json()
    assert body["months"] == {}
    assert body["overall"] is None
