"""История переоценок активов.

Цена актива, введённая вручную, не заменяет прежнюю, а добавляет точку: по
этим точкам строится график капитала, и затирание прошлого переписывало бы
историю задним числом. Люди этого не ждут — спрашивают, почему старая цена
«не убралась», — поэтому поведение закреплено проверками, а не только
комментарием.
"""
from decimal import Decimal

from httpx import AsyncClient


async def test_changing_a_price_adds_a_point_and_keeps_the_old_one(client: AsyncClient):
    """Правка цены историю не затирает.

    Актив стоил столько-то тогда и столько-то сейчас, и график капитала
    строится по этим точкам: затирая прошлое, человек переписывал бы
    собственную историю задним числом. Люди этого не ждут и спрашивают,
    почему старая цена «не убралась», — поэтому поведение закреплено здесь.
    """
    asset = (
        await client.post(
            "/assets",
            json={
                "name": "Ноутбук",
                "asset_class": "other",
                "value": "80000.00",
                "as_of_date": "2021-09-01",
            },
        )
    ).json()

    await client.post(
        f"/assets/{asset['id']}/valuations", json={"value": "25000.00", "as_of_date": "2026-09-10"}
    )

    history = (await client.get(f"/assets/{asset['id']}/valuations")).json()
    assert [(row["as_of_date"], Decimal(row["value"])) for row in history] == [
        ("2021-09-01", Decimal("80000.00")),
        ("2026-09-10", Decimal("25000.00")),
    ]
    # Текущая цена — последняя по дате.
    current = next(row for row in (await client.get("/assets")).json() if row["id"] == asset["id"])
    assert Decimal(current["current_value"]) == Decimal("25000.00")


async def test_a_wrong_point_can_be_removed(client: AsyncClient):
    """Ошибка ввода — единственная причина, по которой точку убирают."""
    asset = (
        await client.post(
            "/assets",
            json={"name": "Ноутбук", "asset_class": "other", "value": "80000.00", "as_of_date": "2021-09-01"},
        )
    ).json()
    await client.post(
        f"/assets/{asset['id']}/valuations", json={"value": "2500000.00", "as_of_date": "2026-09-10"}
    )
    history = (await client.get(f"/assets/{asset['id']}/valuations")).json()
    typo = next(row for row in history if row["as_of_date"] == "2026-09-10")

    resp = await client.delete(f"/assets/{asset['id']}/valuations/{typo['id']}")
    assert resp.status_code == 204, resp.text

    current = next(row for row in (await client.get("/assets")).json() if row["id"] == asset["id"])
    # Текущей снова стала предыдущая точка.
    assert Decimal(current["current_value"]) == Decimal("80000.00")


async def test_the_last_valuation_cannot_be_removed(client: AsyncClient):
    """Актив без цены не показать нигде: вместо исправленной ошибки
    получился бы актив-невидимка. Удалять надо сам актив."""
    asset = (
        await client.post(
            "/assets",
            json={"name": "Ноутбук", "asset_class": "other", "value": "80000.00", "as_of_date": "2021-09-01"},
        )
    ).json()
    only = (await client.get(f"/assets/{asset['id']}/valuations")).json()[0]

    resp = await client.delete(f"/assets/{asset['id']}/valuations/{only['id']}")
    assert resp.status_code == 400
