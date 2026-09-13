"""Операция, разделённая между несколькими людьми.

Долг вернули трое одним переводом. В выписке банка это одна операция, и три
записи в приложении означали бы, что оно перестало сходиться с выпиской —
ровно та причина, по которой у операции когда-то появилась разбивка по
категориям.

Ось здесь своя, отдельная от категорий: та отвечает на «на что», эта на «от
кого». Вид расчёта — заём, безвозвратно, транзит — остаётся на самой
операции: трое, вернувшие долг, вернули именно долг.
"""
from decimal import Decimal

from httpx import AsyncClient


async def _person(client: AsyncClient, name: str) -> dict:
    resp = await client.post("/counterparties", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _account(client: AsyncClient) -> dict:
    resp = await client.post("/accounts", json={"name": "Карта", "kind": "checking"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _payload(account_id: int, **extra) -> dict:
    payload = {
        "account_id": account_id,
        "type": "external_in",
        "amount": "5000.00",
        "description": "Вернули долг",
        "date": "2026-03-05",
        "settlement_kind": "repayment",
    }
    payload.update(extra)
    return payload


async def _settlements(client: AsyncClient) -> dict[str, dict]:
    resp = await client.get("/settlements")
    assert resp.status_code == 200, resp.text
    return {row["name"]: row for row in resp.json()}


async def test_one_transfer_splits_between_three_people(client: AsyncClient):
    """Главное: в приложении одна операция, а в расчётах — три человека."""
    account = await _account(client)
    first = await _person(client, "Первый")
    second = await _person(client, "Второй")
    third = await _person(client, "Третий")

    resp = await client.post(
        "/transactions",
        json=_payload(
            account["id"],
            counterparty_splits=[
                {"counterparty_id": first["id"], "amount": "2000.00"},
                {"counterparty_id": second["id"], "amount": "2000.00"},
                {"counterparty_id": third["id"], "amount": "1000.00"},
            ],
        ),
    )
    assert resp.status_code == 201, resp.text
    assert len(resp.json()["counterparty_splits"]) == 3

    # Операция осталась одной: остаток счёта вырос ровно на пять тысяч.
    listed = next(row for row in (await client.get("/accounts")).json() if row["id"] == account["id"])
    assert Decimal(listed["balance"]) == Decimal("5000.00")

    settlements = await _settlements(client)
    assert Decimal(settlements["Первый"]["received"]) == Decimal("2000.00")
    assert Decimal(settlements["Второй"]["received"]) == Decimal("2000.00")
    assert Decimal(settlements["Третий"]["received"]) == Decimal("1000.00")


async def test_the_split_replaces_the_counterparty(client: AsyncClient):
    """Два ответа на вопрос «от кого» означали бы, что операция посчитана
    дважды."""
    account = await _account(client)
    first = await _person(client, "Первый")
    second = await _person(client, "Второй")

    resp = await client.post(
        "/transactions",
        json=_payload(
            account["id"],
            counterparty_id=first["id"],
            counterparty_splits=[
                {"counterparty_id": first["id"], "amount": "2500.00"},
                {"counterparty_id": second["id"], "amount": "2500.00"},
            ],
        ),
    )
    assert resp.status_code == 422, resp.text


async def test_a_single_share_is_not_a_split(client: AsyncClient):
    """Одна строка — это тот же контрагент в обход поля."""
    account = await _account(client)
    only = await _person(client, "Единственный")

    resp = await client.post(
        "/transactions",
        json=_payload(
            account["id"],
            counterparty_splits=[{"counterparty_id": only["id"], "amount": "5000.00"}],
        ),
    )
    assert resp.status_code == 422, resp.text


async def test_the_shares_must_add_up_exactly(client: AsyncClient):
    """Разбивка, не сходящаяся с операцией, — это молча потерянные или
    выдуманные деньги на чьём-то счету."""
    account = await _account(client)
    first = await _person(client, "Первый")
    second = await _person(client, "Второй")

    resp = await client.post(
        "/transactions",
        json=_payload(
            account["id"],
            counterparty_splits=[
                {"counterparty_id": first["id"], "amount": "2000.00"},
                {"counterparty_id": second["id"], "amount": "2000.00"},
            ],
        ),
    )
    assert resp.status_code == 422, resp.text


async def test_only_settlements_can_be_split_between_people(client: AsyncClient):
    """У обычной траты нет второй стороны, и делить её между людьми
    нечего."""
    account = await _account(client)
    first = await _person(client, "Первый")
    second = await _person(client, "Второй")

    resp = await client.post(
        "/transactions",
        json=_payload(
            account["id"],
            type="expense",
            settlement_kind=None,
            counterparty_splits=[
                {"counterparty_id": first["id"], "amount": "2500.00"},
                {"counterparty_id": second["id"], "amount": "2500.00"},
            ],
        ),
    )
    assert resp.status_code == 422, resp.text


async def test_a_share_of_a_loan_becomes_that_persons_debt(client: AsyncClient):
    """Вид расчёта один на операцию: заняли — значит, должны оба, каждый
    свою долю."""
    account = await _account(client)
    first = await _person(client, "Первый")
    second = await _person(client, "Второй")

    resp = await client.post(
        "/transactions",
        json=_payload(
            account["id"],
            type="external_out",
            settlement_kind="loan_out",
            counterparty_splits=[
                {"counterparty_id": first["id"], "amount": "3000.00"},
                {"counterparty_id": second["id"], "amount": "2000.00"},
            ],
        ),
    )
    assert resp.status_code == 201, resp.text

    settlements = await _settlements(client)
    assert Decimal(settlements["Первый"]["owed_to_me"]) == Decimal("3000.00")
    assert Decimal(settlements["Второй"]["owed_to_me"]) == Decimal("2000.00")


async def test_the_person_filter_finds_a_split_transaction(client: AsyncClient):
    """Без этого «показать всё по человеку» молча теряло бы именно те
    операции, ради которых разбивку и завели."""
    account = await _account(client)
    first = await _person(client, "Первый")
    second = await _person(client, "Второй")
    await client.post(
        "/transactions",
        json=_payload(
            account["id"],
            counterparty_splits=[
                {"counterparty_id": first["id"], "amount": "2500.00"},
                {"counterparty_id": second["id"], "amount": "2500.00"},
            ],
        ),
    )

    found = (await client.get(f"/transactions?counterparty_id={second['id']}")).json()

    assert found["total"] == 1


async def test_editing_replaces_the_whole_split(client: AsyncClient):
    """Список заменяет разбивку целиком — как и у категорий: правка это
    переписывание того, что было, а не дописывание строк."""
    account = await _account(client)
    first = await _person(client, "Первый")
    second = await _person(client, "Второй")
    created = await client.post(
        "/transactions",
        json=_payload(
            account["id"],
            counterparty_splits=[
                {"counterparty_id": first["id"], "amount": "2500.00"},
                {"counterparty_id": second["id"], "amount": "2500.00"},
            ],
        ),
    )

    resp = await client.patch(
        f"/transactions/{created.json()['id']}",
        json={
            "counterparty_splits": [
                {"counterparty_id": first["id"], "amount": "4000.00"},
                {"counterparty_id": second["id"], "amount": "1000.00"},
            ]
        },
    )
    assert resp.status_code == 200, resp.text

    settlements = await _settlements(client)
    assert Decimal(settlements["Первый"]["received"]) == Decimal("4000.00")
    assert Decimal(settlements["Второй"]["received"]) == Decimal("1000.00")


async def test_a_share_for_a_person_who_does_not_exist_is_refused(client: AsyncClient):
    """Схема знает форму запроса, но не содержимое справочника: номер
    несуществующего человека прошёл бы её насквозь и оставил долю, которая
    ничья."""
    account = await _account(client)
    first = await _person(client, "Первый")

    resp = await client.post(
        "/transactions",
        json=_payload(
            account["id"],
            counterparty_splits=[
                {"counterparty_id": first["id"], "amount": "2500.00"},
                {"counterparty_id": 9999, "amount": "2500.00"},
            ],
        ),
    )
    assert resp.status_code == 400, resp.text
