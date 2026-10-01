"""Поля актива не теряются по дороге.

Оба места — и создание, и ответ — раньше перечисляли поля руками, и список
разошёлся со схемой: «личное пользование» не доходило до базы при создании
и не возвращалось наружу никогда. Форма правки читает ответ, видит пусто и
при следующем сохранении отправляет «нет» — то есть отметка не только не
показывалась, но и стиралась.

Валюта по умолчанию была долларом, наследством оригинала. На рублёвой
установке новый актив оказывался долларовым и в рублёвый капитал не
попадал вовсе: капитал считается в одной валюте и ничего не переводит.
"""
from decimal import Decimal

from httpx import AsyncClient


async def _create(client: AsyncClient, **overrides) -> dict:
    payload = {
        "name": "Квартира",
        "asset_class": "real_estate",
        "value": "10000000.00",
        "as_of_date": "2026-10-01",
    }
    payload.update(overrides)
    resp = await client.post("/assets", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_a_new_asset_takes_the_install_currency(client: AsyncClient):
    """Валюта не указана — значит валюта установки, как и у счёта."""
    base = (await client.get("/settings")).json()["currency"]
    asset = await _create(client)
    assert asset["currency"] == base


async def test_a_foreign_asset_keeps_its_own_currency(client: AsyncClient):
    """Имущество за границей бывает — просто это не умолчание."""
    asset = await _create(client, currency="EUR")
    assert asset["currency"] == "EUR"


async def test_personal_use_survives_creation(client: AsyncClient):
    """Отмеченное при создании доходит до базы и возвращается наружу."""
    asset = await _create(client, is_personal_use=True)
    assert asset["is_personal_use"] is True

    listed = {item["id"]: item for item in (await client.get("/assets")).json()}
    assert listed[asset["id"]]["is_personal_use"] is True


async def test_editing_something_else_does_not_clear_personal_use(client: AsyncClient):
    """Правка названия не снимает отметку.

    Снимала: форма читала ответ без флага и отправляла обратно «нет».
    """
    asset = await _create(client, is_personal_use=True)
    resp = await client.patch(f"/assets/{asset['id']}", json={"name": "Квартира у моря"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_personal_use"] is True


async def test_personal_use_can_be_taken_off(client: AsyncClient):
    """Снять отметку по-прежнему можно — она просто больше не снимается сама."""
    asset = await _create(client, is_personal_use=True)
    resp = await client.patch(f"/assets/{asset['id']}", json={"is_personal_use": False})
    assert resp.json()["is_personal_use"] is False


async def test_personal_use_is_left_out_of_the_headline_figure(client: AsyncClient):
    """Жильё, в котором живут, в капитал входит, а в «быстрые деньги» нет —
    ради этого отметка и существует, и потерянная она обесценивала её."""
    await _create(client, is_personal_use=True)
    summary = (await client.get("/net-worth/summary", params={"range": "all"})).json()
    assert summary["personal_use"] == "10000000.00"


async def test_the_breakdowns_only_count_assets_of_the_shown_currency(client: AsyncClient):
    """Разрезы по типу и риску считают то же, что и сам капитал.

    Капитал считается в одной валюте и ничего не переводит, а разрезы
    брали активы всех валют: в рублёвом виде долларовая машина давала
    «1 актив · 0,00 ₽» и её содержание в долларах, подписанное рублём.
    """
    base = (await client.get("/settings")).json()["currency"]
    await _create(
        client, name="Машина", asset_class="vehicles", value="500000.00",
        currency="USD" if base != "USD" else "EUR",
        capital_role="drain", monthly_cash_flow="-500.00",
    )

    summary = (await client.get("/net-worth/summary", params={"range": "all"})).json()
    roles = {item["role"]: item for item in summary["capital_roles"]}
    assert roles["drain"]["count"] == 0
    assert Decimal(roles["drain"]["monthly_cash_flow"]) == Decimal("0")
    # А в своей валюте он на месте.
    other = (
        await client.get(
            "/net-worth/summary",
            params={"range": "all", "currency": "USD" if base != "USD" else "EUR"},
        )
    ).json()
    assert {item["role"]: item for item in other["capital_roles"]}["drain"]["count"] == 1
async def test_a_valuation_can_be_corrected(client: AsyncClient):
    """Опечатка в цене правится, а не удаляется и вводится заново.

    Раньше у точки истории был только крестик: между удалением и повторной
    записью ряд, по которому строится кривая капитала, какое-то время
    неверен.
    """
    asset = await _create(client)
    valuations = (await client.get(f"/assets/{asset['id']}/valuations")).json()
    point = valuations[0]

    resp = await client.patch(
        f"/assets/{asset['id']}/valuations/{point['id']}", json={"value": "9500000.00"}
    )
    assert resp.status_code == 200, resp.text
    assert Decimal(resp.json()["current_value"]) == Decimal("9500000.00")


async def test_a_valuation_can_move_to_another_day(client: AsyncClient):
    """Ошиблись датой — переносится без потери цены."""
    asset = await _create(client)
    point = (await client.get(f"/assets/{asset['id']}/valuations")).json()[0]

    resp = await client.patch(
        f"/assets/{asset['id']}/valuations/{point['id']}", json={"as_of_date": "2026-09-15"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["as_of_date"] == "2026-09-15"


async def test_two_prices_for_one_day_are_refused(client: AsyncClient):
    """День у оценки один: перенос на занятую дату отклоняется.

    Затереть чужую запись молча было бы хуже отказа — две цены на один
    день это не вторая оценка, а потерянная первая.
    """
    asset = await _create(client)
    await client.post(
        f"/assets/{asset['id']}/valuations",
        json={"value": "9000000.00", "as_of_date": "2026-09-15"},
    )
    points = (await client.get(f"/assets/{asset['id']}/valuations")).json()
    october = next(point for point in points if point["as_of_date"] == "2026-10-01")

    resp = await client.patch(
        f"/assets/{asset['id']}/valuations/{october['id']}", json={"as_of_date": "2026-09-15"}
    )
    assert resp.status_code == 409, resp.text
    # Обе записи на месте: отказ ничего не испортил.
    assert len((await client.get(f"/assets/{asset['id']}/valuations")).json()) == 2


async def test_someone_elses_valuation_is_not_found(client: AsyncClient):
    """Точка чужого актива правке не поддаётся."""
    first = await _create(client)
    second = await _create(client, name="Дача")
    point = (await client.get(f"/assets/{first['id']}/valuations")).json()[0]

    resp = await client.patch(
        f"/assets/{second['id']}/valuations/{point['id']}", json={"value": "1.00"}
    )
    assert resp.status_code == 404
