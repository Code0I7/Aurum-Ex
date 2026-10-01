"""Произвольный период у капитала.

Готовые периоды отвечают на «как было в последнее время», свой — на «а что
было тогда-то». Проверяется, что даты действительно ограничивают ряд и что
границы остаются честными: раньше первой записи капитал неизвестен, позже
сегодня — не существует.
"""
from datetime import date, timedelta

from httpx import AsyncClient

from tests.helpers import txn_payload


async def _summary(client: AsyncClient, **params) -> dict:
    resp = await client.get("/net-worth/summary", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_custom_range_bounds_the_series(client: AsyncClient, account_id):
    await client.post("/transactions", json=txn_payload(account_id, amount="100.00", date="2024-05-10"))
    await client.post("/transactions", json=txn_payload(account_id, amount="100.00", date="2025-05-10"))

    summary = await _summary(client, range="custom", start_date="2024-06-01", end_date="2024-12-31")
    dates = [point["date"] for point in summary["series"]]
    assert dates[0] == "2024-06-01"
    assert dates[-1] == "2024-12-31"


async def test_start_is_never_earlier_than_the_first_record(client: AsyncClient, account_id):
    """Ровная линия по нулю за годы, когда учёта не было, — это
    утверждение «капитал тогда был нулевым». На самом деле он был
    неизвестен, и разница существенная."""
    await client.post("/transactions", json=txn_payload(account_id, amount="100.00", date="2025-05-10"))

    summary = await _summary(client, range="custom", start_date="2015-01-01", end_date="2025-12-31")
    assert summary["series"][0]["date"] >= "2025-05-10"


async def test_end_is_never_later_than_today(client: AsyncClient, account_id):
    """Капитал завтрашнего дня приложению неизвестен, и продолжать им
    сегодняшний значило бы выдать догадку за факт."""
    await client.post("/transactions", json=txn_payload(account_id, amount="100.00", date="2026-01-10"))

    future = (date.today() + timedelta(days=90)).isoformat()
    summary = await _summary(client, range="custom", start_date="2026-01-01", end_date=future)
    assert summary["series"][-1]["date"] == date.today().isoformat()


async def test_inverted_range_gives_one_day_not_an_error(client: AsyncClient, account_id):
    """Перевёрнутый диапазон — промах на один щелчок в выпадающем списке,
    а не повод показывать ошибку вместо графика."""
    await client.post("/transactions", json=txn_payload(account_id, amount="100.00", date="2024-05-10"))

    summary = await _summary(client, range="custom", start_date="2025-06-01", end_date="2024-06-01")
    assert len(summary["series"]) == 1


async def test_presets_still_work_without_dates(client: AsyncClient, account_id):
    """Готовые периоды не должны зависеть от того, что появился свой."""
    await client.post("/transactions", json=txn_payload(account_id, amount="100.00", date="2026-01-10"))

    summary = await _summary(client, range="all")
    assert summary["range"] == "all"
    assert summary["series"]
