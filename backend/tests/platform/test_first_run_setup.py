"""Первичная настройка: язык и валюта установки.

До этого выбор делался за человека — валюта бралась из `.env`, а язык не
хранился на сервере вовсе, поэтому единицы измерения заводились по-русски
всем. Здесь проверяется, что выбор на экране настройки доходит до всего, на
что он влияет, и — так же важно — не трогает того, чего касаться не должен.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.currency import Currency
from app.models.unit import Unit

pytestmark = pytest.mark.asyncio


async def test_setup_without_choice_keeps_defaults(anon_client: AsyncClient, session: AsyncSession) -> None:
    """Старый фронтенд языка и валюты не шлёт — настройка обязана работать."""
    resp = await anon_client.post("/auth/setup", json={"username": "admin", "password": "test-password-123"})
    assert resp.status_code == 201, resp.text

    settings = (await anon_client.get("/settings")).json()
    assert settings["language"] == "ru"
    names = {unit.name for unit in (await session.execute(select(Unit))).scalars().all()}
    assert "кг" in names and "шт" in names


async def test_setup_in_english_renames_units(anon_client: AsyncClient, session: AsyncSession) -> None:
    resp = await anon_client.post(
        "/auth/setup",
        json={"username": "admin", "password": "test-password-123", "language": "en", "currency": "EUR"},
    )
    assert resp.status_code == 201, resp.text

    settings = (await anon_client.get("/settings")).json()
    assert settings["language"] == "en"
    assert settings["currency"] == "EUR"

    names = {unit.name for unit in (await session.execute(select(Unit))).scalars().all()}
    assert {"kg", "g", "l", "ml", "pcs", "pack", "m", "service"} <= names
    assert "кг" not in names


async def test_setup_currency_reaches_account_and_directory(
    anon_client: AsyncClient, session: AsyncSession
) -> None:
    """Счёт из засева и справочник валют идут за выбором.

    Иначе человек, выбравший лей, получает счёт в рублях и пустой курс:
    сводные суммы приводятся к валюте установки, а её нет в справочнике."""
    resp = await anon_client.post(
        "/auth/setup",
        json={"username": "admin", "password": "test-password-123", "language": "ru", "currency": "MDL"},
    )
    assert resp.status_code == 201, resp.text

    accounts = (await session.execute(select(Account))).scalars().all()
    assert [account.currency for account in accounts] == ["MDL"]
    codes = {code for (code,) in await session.execute(select(Currency.code))}
    assert "MDL" in codes


async def test_setup_leaves_a_used_account_alone(
    anon_client: AsyncClient, client: AsyncClient, session: AsyncSession
) -> None:
    """Валюта счёта с операциями не меняется задним числом.

    Сценарий узкий, но последствия тяжёлые: суммы уже записаны, и смена
    валюты счёта переписала бы их смысл, не тронув ни одной цифры."""
    account_id = (await client.get("/accounts")).json()[0]["id"]
    created = await client.post(
        "/transactions",
        json={"account_id": account_id, "type": "expense", "amount": "100.00", "date": "2026-01-10"},
    )
    assert created.status_code == 201, created.text

    # Вторая настройка на настроенной установке и так закрыта — проверяем
    # сам перенос валюты, вызывая его напрямую.
    from app.services.setup_service import apply_first_run_choice

    await apply_first_run_choice(session, currency="USD")
    account = await session.get(Account, account_id)
    await session.refresh(account)
    assert account.currency != "USD"


async def test_setup_keeps_renamed_and_custom_units(anon_client: AsyncClient, session: AsyncSession) -> None:
    """Переименование трогает только засеянный набор.

    Единица, заведённая человеком, и единица, которую он переименовал сам,
    переживают смену языка: это его данные, а не подпись интерфейса."""
    from app.models.enums import UnitKind

    session.add(Unit(name="банка", kind=UnitKind.COUNT, factor=1, is_base=False, sort_order=99))
    unit = (await session.execute(select(Unit).where(Unit.name == "оплата"))).scalar_one()
    unit.name = "визит"
    await session.commit()

    resp = await anon_client.post(
        "/auth/setup",
        json={"username": "admin", "password": "test-password-123", "language": "en"},
    )
    assert resp.status_code == 201, resp.text

    names = {row.name for row in (await session.execute(select(Unit))).scalars().all()}
    assert "банка" in names
    assert "визит" in names
    assert "service" not in names
    assert "kg" in names
