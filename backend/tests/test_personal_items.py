"""Личные вещи: свой вид имущества и выбор, считать ли их размещением.

Техника, мебель и инструменты оседали в «прочем», и на рабочей установке
четыре пятых имущества оказались в строке, которая ничего не называет.
Теперь у них свой вид.

Вторая половина — про риск. Уровни риска существуют ради правила
«столько-то капитала размещено без риска, не больше столько-то под
риском», и правило это про размещение: компьютер, на котором работают, не
выбирали как ставку, и предупреждение о рискованном размещении
срабатывало на наушники. Правильного ответа нет — обесценивается и
телефон, — поэтому это настройка, и по умолчанию считается, как считалось.
"""
from decimal import Decimal

from httpx import AsyncClient


async def _asset(client: AsyncClient, name: str, value: str, **overrides) -> dict:
    payload = {
        "name": name,
        "asset_class": "personal_items",
        "value": value,
        "as_of_date": "2026-09-01",
    }
    payload.update(overrides)
    resp = await client.post("/assets", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _summary(client: AsyncClient) -> dict:
    resp = await client.get("/net-worth/summary", params={"range": "all"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _tiers(summary: dict) -> dict[str, dict]:
    return {tier["risk_level"]: tier for tier in summary["risk_levels"]}


async def test_personal_items_are_their_own_class(client: AsyncClient):
    """Техника больше не «прочее»: у неё своя строка в разбивке."""
    await _asset(client, "Компьютер", "208000.00")

    breakdown = {item["key"]: item for item in (await _summary(client))["breakdown"]}
    assert Decimal(breakdown["personal_items"]["amount"]) == Decimal("208000.00")
    assert Decimal(breakdown["other"]["amount"]) == Decimal("0")


async def test_other_still_takes_what_has_no_class(client: AsyncClient):
    """«Прочее» не исчезло — оно просто перестало быть свалкой по умолчанию."""
    await _asset(client, "Доля в чём-то", "5000.00", asset_class="other")

    breakdown = {item["key"]: item for item in (await _summary(client))["breakdown"]}
    assert Decimal(breakdown["other"]["amount"]) == Decimal("5000.00")
    assert Decimal(breakdown["personal_items"]["amount"]) == Decimal("0")


async def test_personal_belongings_count_in_risk_by_default(client: AsyncClient):
    """По умолчанию ничего не меняется: обновление не трогает чужие числа."""
    assert (await client.get("/settings")).json()["risk_counts_personal_use"] is True

    await _asset(client, "Компьютер", "208000.00", is_personal_use=True, risk_level="medium")

    tiers = _tiers(await _summary(client))
    assert Decimal(tiers["medium"]["total_value"]) == Decimal("208000.00")
    assert tiers["medium"]["percent"] == 100.0


async def test_switching_the_setting_off_takes_them_out_of_the_risk_view(client: AsyncClient):
    """Выключено — личные вещи из разреза уходят.

    Разрез тогда отвечает на «как размещено то, что размещено», а не на
    «из чего состоит имущество»: на второй вопрос отвечает разбивка по
    видам, и она личные вещи по-прежнему показывает.
    """
    await _asset(client, "Компьютер", "208000.00", is_personal_use=True, risk_level="medium")
    await _asset(
        client, "Вложение", "50000.00", asset_class="investments", risk_level="high"
    )

    resp = await client.patch("/settings", json={"risk_counts_personal_use": False})
    assert resp.status_code == 200, resp.text

    summary = await _summary(client)
    tiers = _tiers(summary)
    assert Decimal(tiers["medium"]["total_value"]) == Decimal("0")
    assert Decimal(tiers["high"]["total_value"]) == Decimal("50000.00")
    # А в разбивке по видам они на месте: вещь не перестала существовать.
    breakdown = {item["key"]: item for item in summary["breakdown"]}
    assert Decimal(breakdown["personal_items"]["amount"]) == Decimal("208000.00")
    # И отдельная строка «личное пользование» их тоже считает.
    assert Decimal(summary["personal_use"]) == Decimal("208000.00")


async def test_an_asset_not_for_personal_use_stays_in_the_risk_view(client: AsyncClient):
    """Выключатель про личное пользование, а не про вид имущества.

    Сдаваемая квартира — недвижимость, но не личного пользования, и
    размещением она как раз является.
    """
    await _asset(
        client,
        "Сдаётся",
        "3000000.00",
        asset_class="real_estate",
        is_personal_use=False,
        risk_level="medium",
    )
    await client.patch("/settings", json={"risk_counts_personal_use": False})

    tiers = _tiers(await _summary(client))
    assert Decimal(tiers["medium"]["total_value"]) == Decimal("3000000.00")


async def test_the_warning_stops_firing_over_headphones(client: AsyncClient):
    """Ради этого настройка и нужна.

    На рабочей установке четыре гаджета давали 80% «не низкого» риска при
    пороге 20%, и приложение предупреждало о рискованном размещении
    наушников.
    """
    await _asset(client, "Компьютер", "208000.00", is_personal_use=True, risk_level="medium")
    await _asset(client, "Наушники", "4500.00", is_personal_use=True, risk_level="medium")

    keys = {alert["key"] for alert in (await client.get("/insights/alerts")).json()["alerts"]}
    assert "risky_allocation_exceeded" in keys

    await client.patch("/settings", json={"risk_counts_personal_use": False})

    keys = {alert["key"] for alert in (await client.get("/insights/alerts")).json()["alerts"]}
    assert "risky_allocation_exceeded" not in keys


async def test_the_choice_survives_a_backup(client: AsyncClient):
    """Настройка — часть установки, и восстановление её не теряет."""
    await client.patch("/settings", json={"risk_counts_personal_use": False})
    payload = (await client.get("/backup/export")).json()
    assert payload["app_settings"]["risk_counts_personal_use"] is False

    await client.patch("/settings", json={"risk_counts_personal_use": True})
    resp = await client.post("/backup/import", json=payload)
    assert resp.status_code == 200, resp.text
    assert (await client.get("/settings")).json()["risk_counts_personal_use"] is False
