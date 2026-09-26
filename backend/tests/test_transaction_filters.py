"""Отбор списка операций: участник, «участник не указан» и банк счёта.

Участника заполняют не всегда, и найти операции, где его забыли поставить,
иначе нельзя вовсе. Банк отбирает все свои счета сразу: у одного банка бывает
и карта, и рассрочка, и сверять выписку удобнее целиком.
"""
from httpx import AsyncClient


async def _account(client: AsyncClient, name: str, bank_id: int | None = None) -> int:
    payload = {"name": name, "kind": "checking", "currency": "RUB"}
    if bank_id is not None:
        payload["bank_id"] = bank_id
    resp = await client.post("/accounts", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _bank(client: AsyncClient, name: str) -> int:
    resp = await client.post("/banks", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _participant(client: AsyncClient, name: str) -> int:
    resp = await client.post("/participants", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _spend(client: AsyncClient, account_id: int, description: str, **extra) -> dict:
    resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "100.00",
            "description": description,
            "date": "2026-09-10",
            **extra,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _descriptions(client: AsyncClient, **params) -> set[str]:
    resp = await client.get("/transactions", params=params)
    assert resp.status_code == 200, resp.text
    return {row["description"] for row in resp.json()["items"]}


async def test_filter_by_participant(client: AsyncClient, account_id):
    son = await _participant(client, "Сын")
    cat = await _participant(client, "Кот")
    await _spend(client, account_id, "Школа", participant_id=son)
    await _spend(client, account_id, "Корм", participant_id=cat)
    await _spend(client, account_id, "Бензин")

    assert await _descriptions(client, participant_id=son) == {"Школа"}


async def test_filter_by_missing_participant(client: AsyncClient, account_id):
    """Так находятся операции, где участника забыли указать."""
    son = await _participant(client, "Сын")
    await _spend(client, account_id, "Школа", participant_id=son)
    await _spend(client, account_id, "Бензин")
    await _spend(client, account_id, "Хлеб")

    assert await _descriptions(client, no_participant=True) == {"Бензин", "Хлеб"}
    # Общее число тоже считается по отобранным, а не по всем: иначе
    # страницы обещали бы строки, которых в отборе нет.
    body = (await client.get("/transactions", params={"no_participant": True})).json()
    assert body["total"] == 2


async def test_filter_by_bank_takes_all_its_accounts(client: AsyncClient):
    bank = await _bank(client, "Первый банк")
    other_bank = await _bank(client, "Второй банк")
    card = await _account(client, "Карта", bank)
    instalment = await _account(client, "Рассрочка", bank)
    stranger = await _account(client, "Чужая карта", other_bank)
    await _spend(client, card, "Продукты")
    await _spend(client, instalment, "Телефон")
    await _spend(client, stranger, "Бензин")

    assert await _descriptions(client, bank_id=bank) == {"Продукты", "Телефон"}


async def test_bank_filter_sees_both_sides_of_a_transfer(client: AsyncClient):
    """Перевод с карты банка на чужой счёт обязан попасть в отбор по банку и
    с той стороны, куда он пришёл: иначе движение видно половиной."""
    bank = await _bank(client, "Первый банк")
    card = await _account(client, "Карта", bank)
    cash = await _account(client, "Наличные")
    resp = await client.post(
        "/transactions",
        json={
            "account_id": cash,
            "transfer_account_id": card,
            "type": "transfer",
            "amount": "500.00",
            "description": "Внесение на карту",
            "date": "2026-09-10",
        },
    )
    assert resp.status_code == 201, resp.text

    assert await _descriptions(client, bank_id=bank) == {"Внесение на карту"}


async def test_excluded_rows_can_be_hidden(client: AsyncClient, account_id):
    """По умолчанию «не учитывать» видно наравне с остальным — их и заводят,
    чтобы о покупке помнить. Спрятать — отдельное решение."""
    await _spend(client, account_id, "Обычная")
    await _spend(client, account_id, "Возвращённая", is_excluded=True)

    assert await _descriptions(client) == {"Обычная", "Возвращённая"}
    assert await _descriptions(client, include_excluded=False) == {"Обычная"}
