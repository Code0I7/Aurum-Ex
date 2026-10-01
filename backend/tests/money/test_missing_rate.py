"""Операция, для которой нет курса.

Раньше на месте недостающего курса молча стояла единица: покупка на 50 $
становилась 50 ₽ в отчётах. Число выглядит как обычное — ни пометки, ни
ошибки, — и заметно это только по годовым итогам, когда искать причину уже
негде.

Теперь пусто. Операция сохраняется целиком, в итоги не входит и ждёт курса.
Курс прошедшего дня не меняется никогда, поэтому дотянуть его потом и
пересчитать — не «переписать прошлое», а записать его впервые.
"""
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.currency import ExchangeRate
from app.services.currency_service import recompute_missing_base_amounts


async def _account(client: AsyncClient, name: str, currency: str) -> dict:
    resp = await client.post(
        "/accounts", json={"name": name, "kind": "checking", "currency": currency}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _spend(client: AsyncClient, account_id: int, amount: str, on: str = "2026-03-05") -> dict:
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": amount,
            "description": "Покупка",
            "date": on,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _reread(client: AsyncClient, transaction_id: int) -> dict:
    """Операция из списка: отдельного GET по одной у приложения нет."""
    listing = (await client.get("/transactions")).json()["items"]
    return next(row for row in listing if row["id"] == transaction_id)

async def test_a_purchase_without_a_rate_is_saved_but_not_converted(client: AsyncClient):
    """Потерять запись хуже, чем не знать её курс."""
    account = await _account(client, "Долларовая карта", "USD")

    spent = await _spend(client, account["id"], "50.00")

    assert spent["currency"] == "USD"
    assert Decimal(spent["amount"]) == Decimal("50.00")
    # Ни 50 ₽, ни выдуманного курса — пусто.
    assert spent["amount_base"] is None


async def test_the_own_currency_always_converts(client: AsyncClient):
    """Курс валюты установки к самой себе равен единице и в таблице не
    хранится — рублёвым операциям ждать нечего."""
    account = await _account(client, "Рублёвая карта", "RUB")

    spent = await _spend(client, account["id"], "100.00")

    assert Decimal(spent["amount_base"]) == Decimal("100.00")


async def test_an_unconverted_purchase_stays_out_of_the_totals(client: AsyncClient):
    """Единица на её месте втащила бы пятьдесят долларов в капитал как
    пятьдесят рублей."""
    rouble = await _account(client, "Рублёвая карта", "RUB")
    dollar = await _account(client, "Долларовая карта", "USD")
    await _spend(client, rouble["id"], "100.00")
    await _spend(client, dollar["id"], "50.00")

    net_worth = (await client.get("/net-worth/summary?range=all")).json()
    # В капитал вошла только рублёвая трата: −100. Долларовая ждёт курса.
    assert Decimal(net_worth["liquid"]) == Decimal("-100.00")


async def test_a_rate_that_arrives_later_completes_the_purchase(
    client: AsyncClient, session: AsyncSession
):
    """Курс прошедшего дня не меняется никогда, и записать его позже — не
    переписать прошлое, а записать его впервые."""
    account = await _account(client, "Долларовая карта", "USD")
    spent = await _spend(client, account["id"], "50.00", on="2026-03-05")
    assert spent["amount_base"] is None

    session.add(ExchangeRate(code="USD", rate_date=date(2026, 3, 5), rate=Decimal("81.2")))
    await session.commit()

    assert await recompute_missing_base_amounts(session) == 1

    again = await _reread(client, spent["id"])
    assert Decimal(again["amount_base"]) == Decimal("4060.00")


async def test_an_already_converted_purchase_is_never_touched(
    client: AsyncClient, session: AsyncSession
):
    """Посчитанное заморожено навсегда: трата 2022 года так и осталась
    тратой того года, что бы ни делал доллар потом."""
    account = await _account(client, "Долларовая карта", "USD")
    session.add(ExchangeRate(code="USD", rate_date=date(2026, 3, 5), rate=Decimal("81.2")))
    await session.commit()

    spent = await _spend(client, account["id"], "50.00", on="2026-03-05")
    assert Decimal(spent["amount_base"]) == Decimal("4060.00")

    session.add(ExchangeRate(code="USD", rate_date=date(2026, 3, 6), rate=Decimal("99.9")))
    await session.commit()
    assert await recompute_missing_base_amounts(session) == 0

    again = await _reread(client, spent["id"])
    assert Decimal(again["amount_base"]) == Decimal("4060.00")
