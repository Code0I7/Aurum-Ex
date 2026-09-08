"""Переключатель «Точное отображение» — копейки в суммах.

Округление до рубля разумно в годовых итогах и вредно в самой операции:
36,99 показанные как 37 — это уже не то, что записано, и столбец из таких
строк не сходится в сумму. Считает и хранит приложение всегда с копейками;
переключатель влияет только на показ, поэтому проверка здесь одна — что
значение доезжает до клиента и переживает перезапись.
"""
from httpx import AsyncClient


async def test_cents_are_shown_by_default(client: AsyncClient):
    """Показать лишнее хуже, чем скрыть нужное, но соврать хуже обоих —
    поэтому по умолчанию включено."""
    resp = await client.get("/settings")
    assert resp.status_code == 200, resp.text
    assert resp.json()["show_cents"] is True


async def test_the_switch_survives_a_round_trip(client: AsyncClient):
    updated = await client.patch("/settings", json={"show_cents": False})
    assert updated.status_code == 200, updated.text
    assert updated.json()["show_cents"] is False

    assert (await client.get("/settings")).json()["show_cents"] is False


async def test_other_settings_are_untouched_by_the_switch(client: AsyncClient):
    """Частичное обновление не должно сбрасывать соседние поля: валюта,
    выбранная человеком однажды, переживает любой другой переключатель."""
    await client.patch("/settings", json={"currency": "EUR"})
    await client.patch("/settings", json={"show_cents": False})

    body = (await client.get("/settings")).json()
    assert body["currency"] == "EUR"
    assert body["show_cents"] is False
