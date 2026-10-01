"""Валюта счёта.

Счёт держит одну валюту — так они и устроены в жизни: рублёвая карта,
долларовая карта. Валюта операции берётся со счёта, спрашивать её в форме
незачем: списать доллары с рублёвой карты нельзя, а если площадка
конвертировала сама, банк снял рубли, и в операции рубли.

Валюта копируется в операцию при сохранении, а не спрашивается у счёта при
подсчётах. Поэтому сменить её на счёте задним числом мало: операции остались
бы в прежней, и остаток стал бы суммой рублей с долларами как голых чисел.
Раньше по этой причине смена и запрещалась вовсе.

Теперь смена переписывает и операции: валюта у них становится новой, а сумма
в валюте установки считается заново — по курсу на дату самой операции, а не
на сегодня. Сама сумма не трогается: человек ввёл её с чека, поменялось
только то, чем она подписана.

Это правка ошибки при заведении счёта, а не перевод денег из валюты в
валюту. Если счёт действительно вёлся в прежней валюте, а теперь это другая
карта, — это другой счёт. Различить два случая приложение не может, поэтому
предупреждает форма.
"""
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.currency import ExchangeRate


async def _account(client: AsyncClient, name: str, currency: str = "RUB") -> dict:
    resp = await client.post(
        "/accounts", json={"name": name, "kind": "checking", "currency": currency}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _spend(client: AsyncClient, account_id: int, amount: str = "100.00", **extra) -> dict:
    payload = {
        "account_id": account_id,
        "type": "expense",
        "amount": amount,
        "description": "Покупка",
        "date": "2026-03-05",
    }
    payload.update(extra)
    resp = await client.post("/transactions", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _reread(client: AsyncClient, transaction_id: int) -> dict:
    """Операция из списка: отдельного GET по одной у приложения нет."""
    listing = (await client.get("/transactions")).json()["items"]
    return next(row for row in listing if row["id"] == transaction_id)


async def _rate(session: AsyncSession, code: str, value: str, on: str = "2026-03-05") -> None:
    session.add(ExchangeRate(code=code, rate_date=date.fromisoformat(on), rate=Decimal(value)))
    await session.commit()


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


async def test_the_change_relabels_the_transactions(client: AsyncClient, session: AsyncSession):
    """Главное: операции переходят в новую валюту вместе со счётом.

    Оставить их в прежней значило бы получить счёт, где к рублям
    прибавляются доллары как голые числа."""
    account = await _account(client, "Карта", "RUB")
    spent = await _spend(client, account["id"], "100.00")
    assert spent["currency"] == "RUB"
    await _rate(session, "USD", "81.2")

    resp = await client.patch(f"/accounts/{account['id']}", json={"currency": "USD"})
    assert resp.status_code == 200, resp.text

    again = await _reread(client, spent["id"])
    assert again["currency"] == "USD"
    # Сумма та же: её ввели с чека, поменялось только то, чем она подписана.
    assert Decimal(again["amount"]) == Decimal("100.00")
    # А пересчёт в валюту установки — заново, по курсу на дату операции.
    assert Decimal(again["amount_base"]) == Decimal("8120.00")


async def test_the_rate_is_taken_on_the_date_of_the_transaction(
    client: AsyncClient, session: AsyncSession
):
    """Не сегодняшний курс на всю историю: трата 2022 года так и осталась
    тратой того года."""
    account = await _account(client, "Карта", "RUB")
    old = await _spend(client, account["id"], "100.00", date="2026-03-05")
    new = await _spend(client, account["id"], "100.00", date="2026-03-06")
    await _rate(session, "USD", "81.2", on="2026-03-05")
    await _rate(session, "USD", "99.9", on="2026-03-06")

    resp = await client.patch(f"/accounts/{account['id']}", json={"currency": "USD"})
    assert resp.status_code == 200, resp.text

    assert Decimal((await _reread(client, old["id"]))["amount_base"]) == Decimal("8120.00")
    assert Decimal((await _reread(client, new["id"]))["amount_base"]) == Decimal("9990.00")


async def test_a_date_without_a_rate_stays_empty(client: AsyncClient):
    """Ради этого сумма в валюте установки и научилась быть пустой: раньше
    на месте недостающего курса молча стояла единица, и пересчёт записал бы
    её полусотне старых операций разом."""
    account = await _account(client, "Карта", "RUB")
    spent = await _spend(client, account["id"], "100.00")

    resp = await client.patch(f"/accounts/{account['id']}", json={"currency": "USD"})
    assert resp.status_code == 200, resp.text

    again = await _reread(client, spent["id"])
    assert again["currency"] == "USD"
    assert again["amount_base"] is None


async def test_a_transaction_with_its_own_currency_is_left_alone(
    client: AsyncClient, session: AsyncSession
):
    """Смена валюты счёта — не повод трогать то, что указали руками."""
    account = await _account(client, "Карта", "RUB")
    await _rate(session, "USD", "81.2")
    own = await _spend(client, account["id"], "50.00", currency="USD")
    assert own["currency"] == "USD"

    resp = await client.patch(f"/accounts/{account['id']}", json={"currency": "EUR"})
    assert resp.status_code == 200, resp.text

    assert (await _reread(client, own["id"]))["currency"] == "USD"


async def test_a_transfer_belongs_to_the_account_it_left(client: AsyncClient):
    """Перевод записывается один раз, со стороны отправителя: у получателя
    он есть в балансе, но своей строки там нет — и валюту она несёт чужую."""
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
    assert resp.status_code == 200, resp.text

    assert (await _reread(client, moved.json()["id"]))["currency"] == "RUB"


async def test_the_same_currency_is_not_a_change(client: AsyncClient):
    """Форма присылает все поля целиком, и валюта приходит в каждой правке.
    Пересчитывать на ней значило бы переписывать курсы при переименовании."""
    account = await _account(client, "Карта", "RUB")
    spent = await _spend(client, account["id"], "100.00")

    resp = await client.patch(
        f"/accounts/{account['id']}", json={"name": "Карта банка", "currency": "RUB"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Карта банка"
    assert Decimal((await _reread(client, spent["id"]))["amount_base"]) == Decimal("100.00")


async def test_the_account_says_how_many_transactions_it_has(client: AsyncClient):
    """Число нужно форме: «47 операций» читается совсем иначе, чем «все
    операции»."""
    account = await _account(client, "Карта", "RUB")
    await _spend(client, account["id"], "100.00")
    await _spend(client, account["id"], "200.00")

    listed = next(
        row for row in (await client.get("/accounts")).json() if row["id"] == account["id"]
    )
    assert listed["transaction_count"] == 2
