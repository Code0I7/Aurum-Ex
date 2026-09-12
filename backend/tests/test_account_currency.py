"""Валюта счёта.

Счёт держит одну валюту — так они и устроены в жизни: рублёвая карта,
долларовая карта. Валюта операции берётся со счёта, спрашивать её в форме
незачем: списать доллары с рублёвой карты нельзя, а если площадка
конвертировала сама, банк снял рубли, и в операции рубли.

Отсюда единственное правило, которое надо стеречь: валюту счёта меняют, пока
по нему нет операций. Баланс складывается из их сумм, а у каждой своя
валюта, записанная в момент ввода, — смена задним числом дала бы счёт, где к
рублям прибавляются доллары как голые числа.
"""
from httpx import AsyncClient


async def _account(client: AsyncClient, name: str, currency: str = "RUB") -> dict:
    resp = await client.post(
        "/accounts", json={"name": name, "kind": "checking", "currency": currency}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_an_account_keeps_the_currency_it_was_created_with(client: AsyncClient):
    account = await _account(client, "Долларовая карта", "USD")
    assert account["currency"] == "USD"

    listed = next(row for row in (await client.get("/accounts")).json() if row["id"] == account["id"])
    assert listed["currency"] == "USD"


async def test_the_currency_changes_while_the_account_is_empty(client: AsyncClient):
    """Завёл карту и тут же заметил, что выбрал не ту валюту."""
    account = await _account(client, "Карта", "RUB")

    resp = await client.patch(f"/accounts/{account['id']}", json={"currency": "USD"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["currency"] == "USD"


async def test_the_currency_is_frozen_once_money_moved(client: AsyncClient):
    """Иначе остаток стал бы суммой рублей с долларами — молча, без единой
    ошибки на экране."""
    account = await _account(client, "Карта", "RUB")
    spent = await client.post(
        "/transactions",
        json={
            "account_id": account["id"],
            "type": "expense",
            "amount": "100.00",
            "description": "Покупка",
            "date": "2026-03-05",
        },
    )
    assert spent.status_code == 201, spent.text

    resp = await client.patch(f"/accounts/{account['id']}", json={"currency": "USD"})
    assert resp.status_code == 400, resp.text


async def test_the_same_currency_is_not_a_change(client: AsyncClient):
    """Форма присылает все поля целиком, и валюта приходит в каждой правке.
    Отказывать на ней значило бы запретить переименование счёта."""
    account = await _account(client, "Карта", "RUB")
    await client.post(
        "/transactions",
        json={
            "account_id": account["id"],
            "type": "expense",
            "amount": "100.00",
            "description": "Покупка",
            "date": "2026-03-05",
        },
    )

    resp = await client.patch(
        f"/accounts/{account['id']}", json={"name": "Карта банка", "currency": "RUB"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Карта банка"


async def test_a_transfer_counts_as_movement_on_both_sides(client: AsyncClient):
    """Счёт, на который переводили, тоже не пустой — хотя своей колонкой в
    операции он не записан."""
    source = await _account(client, "Откуда", "RUB")
    target = await _account(client, "Куда", "RUB")
    moved = await client.post(
        "/transactions",
        json={
            "account_id": source["id"],
            "transfer_account_id": target["id"],
            "type": "transfer",
            "amount": "500.00",
            "description": "Перевод",
            "date": "2026-03-05",
        },
    )
    assert moved.status_code == 201, moved.text

    resp = await client.patch(f"/accounts/{target['id']}", json={"currency": "USD"})
    assert resp.status_code == 400, resp.text
