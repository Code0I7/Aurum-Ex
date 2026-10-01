"""Перевод между счетами в разных валютах.

Перевод записан одной строкой, со стороны отправителя. Пока обе карты в
одной валюте, этого хватает: сколько ушло, столько и пришло.

Между валютами равенство ломается. Сто евро уходят с евровой карты, а на
рублёвую приходит не сто, а столько, сколько дал банк своим курсом и своей
комиссией. Вывести это число из курса ЦБ нельзя — оно ему не равно и равняться
не обязано, — поэтому вторая сумма спрашивается, а не считается. Разница между
сторонами и есть цена перевода, и видно её только так.
"""
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.currency import ExchangeRate


async def _account(client: AsyncClient, name: str, currency: str, opening: str = "0") -> dict:
    resp = await client.post(
        "/accounts",
        json={"name": name, "kind": "checking", "currency": currency, "opening_balance": opening},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _balance(client: AsyncClient, account_id: int) -> Decimal:
    listed = next(
        row for row in (await client.get("/accounts")).json() if row["id"] == account_id
    )
    return Decimal(listed["balance"])


async def _transfer(
    client: AsyncClient, source: dict, target: dict, amount: str, **extra
) -> "tuple[int, dict]":
    payload = {
        "account_id": source["id"],
        "transfer_account_id": target["id"],
        "type": "transfer",
        "amount": amount,
        "description": "Перевод",
        "date": "2026-03-05",
    }
    payload.update(extra)
    resp = await client.post("/transactions", json=payload)
    return resp.status_code, resp


async def test_a_transfer_inside_one_currency_needs_no_second_amount(client: AsyncClient):
    """Сколько ушло, столько и пришло: второе число было бы копией первого,
    а копия однажды разойдётся с оригиналом."""
    source = await _account(client, "Откуда", "RUB", "1000")
    target = await _account(client, "Куда", "RUB")

    status, resp = await _transfer(client, source, target, "500.00")
    assert status == 201, resp.text
    assert resp.json()["transfer_amount"] is None
    assert resp.json()["transfer_currency"] is None

    assert await _balance(client, source["id"]) == Decimal("500.00")
    assert await _balance(client, target["id"]) == Decimal("500.00")


async def test_a_transfer_between_currencies_is_refused_without_the_second_amount(
    client: AsyncClient,
):
    """Подставить сюда что-нибудь значит выдумать сумму на чужом счёте."""
    source = await _account(client, "Евровая", "EUR", "1000")
    target = await _account(client, "Рублёвая", "RUB")

    status, resp = await _transfer(client, source, target, "100.00")
    assert status == 400, resp.text


async def test_the_destination_gets_what_arrived_not_what_left(client: AsyncClient):
    """Ради этого всё и делалось: сто евро не превращаются в сто рублей."""
    source = await _account(client, "Евровая", "EUR", "1000")
    target = await _account(client, "Рублёвая", "RUB")

    status, resp = await _transfer(
        client, source, target, "100.00", transfer_amount="9500.00"
    )
    assert status == 201, resp.text
    row = resp.json()
    assert Decimal(row["amount"]) == Decimal("100.00")
    assert Decimal(row["transfer_amount"]) == Decimal("9500.00")
    assert row["transfer_currency"] == "RUB"

    assert await _balance(client, source["id"]) == Decimal("900.00")
    assert await _balance(client, target["id"]) == Decimal("9500.00")


async def test_the_second_amount_is_converted_at_the_rate_of_the_day(
    client: AsyncClient, session: AsyncSession
):
    """Пришедшая сумма тоже приводится к валюте установки — иначе разницу
    между сторонами, то есть цену перевода, капиталу не из чего посчитать."""
    session.add(ExchangeRate(code="EUR", rate_date=date(2026, 3, 5), rate=Decimal("98.0")))
    await session.commit()

    source = await _account(client, "Евровая", "EUR", "1000")
    target = await _account(client, "Рублёвая", "RUB")

    _, resp = await _transfer(client, source, target, "100.00", transfer_amount="9500.00")
    row = resp.json()

    # Ушло сто евро по 98 — это 9 800 ₽. Пришло 9 500 ₽. Триста рублей и
    # стоил перевод.
    assert Decimal(row["amount_base"]) == Decimal("9800.00")
    assert Decimal(row["transfer_amount_base"]) == Decimal("9500.00")


async def test_the_second_amount_is_dropped_when_the_currencies_match(client: AsyncClient):
    """Прислать её всё равно можно — форма отправляет поля целиком, — но
    хранить её не за чем: она равна первой."""
    source = await _account(client, "Откуда", "RUB", "1000")
    target = await _account(client, "Куда", "RUB")

    _, resp = await _transfer(client, source, target, "500.00", transfer_amount="500.00")

    assert resp.json()["transfer_amount"] is None


async def test_editing_the_second_amount_moves_the_destination_balance(client: AsyncClient):
    source = await _account(client, "Евровая", "EUR", "1000")
    target = await _account(client, "Рублёвая", "RUB")
    _, created = await _transfer(client, source, target, "100.00", transfer_amount="9500.00")

    resp = await client.patch(
        f"/transactions/{created.json()['id']}", json={"transfer_amount": "9400.00"}
    )
    assert resp.status_code == 200, resp.text

    assert await _balance(client, target["id"]) == Decimal("9400.00")


async def test_a_transfer_that_became_an_expense_loses_its_second_amount(client: AsyncClient):
    """Поле принадлежит переводу. У расхода второй стороны нет вовсе, и
    оставшееся число молча искажало бы остаток."""
    source = await _account(client, "Евровая", "EUR", "1000")
    target = await _account(client, "Рублёвая", "RUB")
    _, created = await _transfer(client, source, target, "100.00", transfer_amount="9500.00")

    resp = await client.patch(
        f"/transactions/{created.json()['id']}",
        json={"type": "expense", "transfer_account_id": None},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["transfer_amount"] is None

    assert await _balance(client, target["id"]) == Decimal("0.00")


async def test_changing_the_destination_currency_keeps_the_balance_still(client: AsyncClient):
    """Смена валюты счёта обещает не трогать числа, а только подпись под
    ними. Перевод, пришедший на этот счёт, до сих пор хранил сумму молча —
    она равнялась отправленной, — и после смены её надо назвать явно, иначе
    остаток сдвинется сам собой."""
    source = await _account(client, "Откуда", "RUB", "1000")
    target = await _account(client, "Куда", "RUB")
    await _transfer(client, source, target, "500.00")
    assert await _balance(client, target["id"]) == Decimal("500.00")

    resp = await client.patch(f"/accounts/{target['id']}", json={"currency": "USD"})
    assert resp.status_code == 200, resp.text

    # Ровно те же пятьсот, теперь долларовые: приложение не знает, сколько
    # пришло на самом деле, и выдумывать не должно.
    assert await _balance(client, target["id"]) == Decimal("500.00")
    listing = (await client.get("/transactions")).json()["items"]
    moved = next(row for row in listing if row["type"] == "transfer")
    assert moved["transfer_currency"] == "USD"
    assert Decimal(moved["transfer_amount"]) == Decimal("500.00")
