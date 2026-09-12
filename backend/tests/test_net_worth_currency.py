"""Капитал по валютам.

Капитал — состояние, а не событие, и переводить его нельзя: сто евро на
евровой карте это сто евро, а не их сегодняшняя цена в рублях и не
вчерашняя. Переводить значило бы каждый день заново переписывать всю
историю графика курсом дня.

Поэтому не один пересчитанный итог, а по величине на валюту и переключатель
между ними. Переводится ровно одно число — «сколько лежит в остальных
валютах», — и только потому, что иначе его не выразить: евро с юанями не
складываются.
"""
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.currency import ExchangeRate


async def _account(client: AsyncClient, name: str, currency: str, amount: str) -> dict:
    """Счёт с деньгами на нём.

    Деньги заводятся доходом, а не начальным остатком: ряд капитала
    строится по операциям, и у счёта без единой записи его просто нет.
    """
    resp = await client.post(
        "/accounts", json={"name": name, "kind": "checking", "currency": currency}
    )
    assert resp.status_code == 201, resp.text
    account = resp.json()

    income = await client.post(
        "/transactions",
        json={
            "account_id": account["id"],
            "type": "income",
            "amount": amount,
            "description": "Поступление",
            "date": "2026-03-05",
        },
    )
    assert income.status_code == 201, income.text
    return account


async def _summary(client: AsyncClient, currency: str | None = None) -> dict:
    query = "range=all" + (f"&currency={currency}" if currency else "")
    resp = await client.get(f"/net-worth/summary?{query}")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_the_capital_of_one_currency_holds_only_that_currency(client: AsyncClient):
    """Долларовый счёт не прибавляет своих цифр к рублёвому итогу — раньше
    сто долларов входили в него как сто рублей."""
    await _account(client, "Рублёвая", "RUB", "1000")
    await _account(client, "Долларовая", "USD", "100")

    body = await _summary(client)

    assert body["currency"] == "RUB"
    assert Decimal(body["current"]) == Decimal("1000.00")


async def test_the_rest_is_converted_once_and_marked_as_such(
    client: AsyncClient, session: AsyncSession
):
    """Единственное переведённое число здесь — «в остальных валютах»:
    сложить доллары с юанями иначе нельзя."""
    session.add(ExchangeRate(code="USD", rate_date=date.today(), rate=Decimal("80.0")))
    await session.commit()

    await _account(client, "Рублёвая", "RUB", "1000")
    await _account(client, "Долларовая", "USD", "100")

    body = await _summary(client)

    assert Decimal(body["other_base"]) == Decimal("8000.00")
    assert Decimal(body["total_base"]) == Decimal("9000.00")


async def test_switching_the_currency_switches_the_question(
    client: AsyncClient, session: AsyncSession
):
    """«Сколько у меня долларов» — это не «сколько мои доллары стоят»."""
    session.add(ExchangeRate(code="USD", rate_date=date.today(), rate=Decimal("80.0")))
    await session.commit()

    await _account(client, "Рублёвая", "RUB", "1000")
    await _account(client, "Долларовая", "USD", "100")

    body = await _summary(client, "USD")

    assert body["currency"] == "USD"
    # Сто долларов, а не восемь тысяч: в своей валюте и без перевода.
    assert Decimal(body["current"]) == Decimal("100.00")
    # А «в остальных» здесь уже рубли — и они как раз приводятся.
    assert Decimal(body["other_base"]) == Decimal("1000.00")


async def test_the_switcher_lists_every_currency_in_play(client: AsyncClient):
    await _account(client, "Рублёвая", "RUB", "1000")
    await _account(client, "Долларовая", "USD", "100")

    body = await _summary(client)

    assert "RUB" in body["currencies"]
    assert "USD" in body["currencies"]


async def test_the_own_currency_stays_in_the_list_when_it_holds_nothing(client: AsyncClient):
    """Переключателю нужно, куда вернуться."""
    body = await _summary(client)

    assert body["currencies"] == ["RUB"]
    assert body["currency"] == "RUB"
