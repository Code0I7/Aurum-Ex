"""Перевод между своими счетами, записанный дважды.

Перевод заносят по выпискам, а выписок две — по одной на банк. Один и тот же
перевод легко попадает в приложение дважды, и тогда остатки врут на всю
сумму, а если половины записаны тратой и доходом — врут и расходы с
доходами. Приложение находит такие пары и предлагает склеить; само не
склеивает никогда.
"""
from decimal import Decimal

from httpx import AsyncClient

from tests.helpers import money

MATCHES = "/transactions/transfer-matches"


async def _account(client: AsyncClient, name: str, currency: str = "RUB") -> int:
    resp = await client.post("/accounts", json={"name": name, "kind": "checking", "currency": currency})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _post(client: AsyncClient, **payload) -> dict:
    resp = await client.post("/transactions", json={"amount": "1206.00", **payload})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _out(client: AsyncClient, account_id: int, on: str, **extra) -> dict:
    return await _post(client, account_id=account_id, type="expense", date=on, **extra)


async def _in(client: AsyncClient, account_id: int, on: str, **extra) -> dict:
    return await _post(client, account_id=account_id, type="income", date=on, **extra)


async def _transfer(client: AsyncClient, source: int, target: int, on: str, **extra) -> dict:
    return await _post(
        client, account_id=source, transfer_account_id=target, type="transfer", date=on, **extra
    )


async def _balances(client: AsyncClient) -> dict[int, Decimal]:
    return {row["id"]: money(row["balance"]) for row in (await client.get("/accounts")).json()}


async def _all_transactions(client: AsyncClient) -> list[dict]:
    return (await client.get("/transactions", params={"page_size": 100})).json()["items"]


async def test_two_halves_from_two_statements_become_one_transfer(client: AsyncClient, categories):
    """Выписка банка-отправителя дала трату, выписка получателя — доход.
    Склейка делает из них один перевод, и он больше не считается ни тратой,
    ни доходом."""
    first = await _account(client, "Первый банк")
    second = await _account(client, "Второй банк")
    spent = await _out(
        client, first, "2026-02-27", description="Перевод себе", category_id=categories["Groceries"]["id"]
    )
    # Около полуночи банки ставят разные даты — разница в день.
    received = await _in(
        client, second, "2026-02-28", description="Пополнение", category_id=categories["Salary"]["id"]
    )
    balances_before = await _balances(client)

    matches = (await client.get(MATCHES)).json()
    assert len(matches) == 1
    assert matches[0]["kind"] == "halves"
    assert matches[0]["keep"]["id"] == spent["id"]
    assert matches[0]["drop"]["id"] == received["id"]

    resp = await client.post(MATCHES + "/merge", json={"first_id": received["id"], "second_id": spent["id"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["kept_id"] == spent["id"]

    rows = await _all_transactions(client)
    assert [row["id"] for row in rows] == [spent["id"]]
    transfer = rows[0]
    assert transfer["type"] == "transfer"
    assert transfer["account_id"] == first
    assert transfer["transfer_account_id"] == second
    assert transfer["category_id"] is None
    assert transfer["date"] == "2026-02-27"
    # Описание каждой половины сохранено: в двух выписках они разные.
    assert transfer["description"] == "Перевод себе · Пополнение"

    # Деньги на счетах те же, что и до склейки…
    assert await _balances(client) == balances_before
    # …но это больше не трата и не доход.
    summary = (await client.get("/dashboard/summary", params={"year": 2026, "month": 2})).json()
    assert money(summary["spent"]) == 0
    assert money(summary["real_income"]) == 0
    assert (await client.get(MATCHES)).json() == []


async def test_sent_and_returned_the_same_day_is_two_transfers(client: AsyncClient):
    """Отправил с одного банка и в тот же день вернул с другого: четыре
    строки двух выписок — это два перевода в разные стороны, а не один и не
    четыре."""
    first = await _account(client, "Первый банк")
    second = await _account(client, "Второй банк")
    out_first = await _out(client, first, "2026-02-27")
    in_second = await _in(client, second, "2026-02-27")
    out_second = await _out(client, second, "2026-02-27")
    in_first = await _in(client, first, "2026-02-27")

    matches = (await client.get(MATCHES)).json()
    pairs = {(match["keep"]["id"], match["drop"]["id"]) for match in matches}
    # Каждая трата склеивается с доходом на ДРУГОМ счёте — направление
    # сохраняется.
    assert pairs == {(out_first["id"], in_second["id"]), (out_second["id"], in_first["id"])}

    for keep, drop in pairs:
        resp = await client.post(MATCHES + "/merge", json={"first_id": keep, "second_id": drop})
        assert resp.status_code == 200, resp.text

    transfers = {(row["account_id"], row["transfer_account_id"]) for row in await _all_transactions(client)}
    assert transfers == {(first, second), (second, first)}


async def test_opposite_transfers_are_not_a_pair(client: AsyncClient):
    """Туда и обратно — два настоящих перевода, склеивать нечего."""
    first = await _account(client, "Первый банк")
    second = await _account(client, "Второй банк")
    await _transfer(client, first, second, "2026-02-27")
    await _transfer(client, second, first, "2026-02-28")

    assert (await client.get(MATCHES)).json() == []


async def test_income_entered_again_for_a_recorded_transfer(client: AsyncClient, categories):
    """Перевод уже записан по выписке отправителя, а по выписке получателя
    тот же приход занесён доходом — удаляется доход."""
    first = await _account(client, "Первый банк")
    second = await _account(client, "Второй банк")
    transfer = await _transfer(client, first, second, "2026-02-27")
    income = await _in(client, second, "2026-02-27", category_id=categories["Salary"]["id"])

    matches = (await client.get(MATCHES)).json()
    assert [(m["kind"], m["keep"]["id"], m["drop"]["id"]) for m in matches] == [
        ("transfer_and_in", transfer["id"], income["id"])
    ]

    await client.post(MATCHES + "/merge", json={"first_id": transfer["id"], "second_id": income["id"]})
    rows = await _all_transactions(client)
    assert [row["id"] for row in rows] == [transfer["id"]]


async def test_expense_entered_again_for_a_recorded_transfer(client: AsyncClient):
    first = await _account(client, "Первый банк")
    second = await _account(client, "Второй банк")
    transfer = await _transfer(client, first, second, "2026-02-27")
    expense = await _out(client, first, "2026-02-28")

    matches = (await client.get(MATCHES)).json()
    assert [(m["kind"], m["keep"]["id"], m["drop"]["id"]) for m in matches] == [
        ("transfer_and_out", transfer["id"], expense["id"])
    ]


async def test_the_same_transfer_twice_keeps_the_earlier_one(client: AsyncClient):
    first = await _account(client, "Первый банк")
    second = await _account(client, "Второй банк")
    earlier = await _transfer(client, first, second, "2026-02-28", description="Из выписки Первый банк")
    later = await _transfer(client, first, second, "2026-02-27")

    matches = (await client.get(MATCHES)).json()
    assert [(m["kind"], m["keep"]["id"], m["drop"]["id"]) for m in matches] == [
        ("transfer_twice", earlier["id"], later["id"])
    ]


async def test_more_than_a_day_apart_is_not_a_pair(client: AsyncClient):
    first = await _account(client, "Первый банк")
    second = await _account(client, "Второй банк")
    await _out(client, first, "2026-02-26")
    await _in(client, second, "2026-02-28")

    assert (await client.get(MATCHES)).json() == []


async def test_a_dismissed_pair_does_not_come_back(client: AsyncClient):
    """Совпадение суммы и дня бывает честным. Отказ помнится, иначе та же
    пара возвращалась бы при каждой загрузке."""
    first = await _account(client, "Первый банк")
    cash = await _account(client, "Наличные")
    spent = await _out(client, first, "2026-02-27")
    received = await _in(client, cash, "2026-02-27")

    resp = await client.post(MATCHES + "/dismiss", json={"first_id": received["id"], "second_id": spent["id"]})
    assert resp.status_code == 204, resp.text
    # Повторный отказ ничего не ломает.
    resp = await client.post(MATCHES + "/dismiss", json={"first_id": spent["id"], "second_id": received["id"]})
    assert resp.status_code == 204, resp.text

    assert (await client.get(MATCHES)).json() == []
    # И обе записи на месте.
    assert len(await _all_transactions(client)) == 2


async def test_excluded_and_split_rows_are_never_halves(client: AsyncClient, categories):
    """«Не учитывать» уже выведено из итогов, а разделённая трата — покупка,
    и склейка молча потеряла бы разбивку."""
    first = await _account(client, "Первый банк")
    second = await _account(client, "Второй банк")
    await _out(client, first, "2026-02-27", is_excluded=True)
    await _in(client, second, "2026-02-27")
    await _out(
        client,
        first,
        "2026-03-10",
        category_id=None,
        splits=[
            {"category_id": categories["Groceries"]["id"], "amount": "1000.00"},
            {"category_id": categories["Transportation"]["id"], "amount": "206.00"},
        ],
    )
    await _in(client, second, "2026-03-10")

    assert (await client.get(MATCHES)).json() == []


async def test_merge_rechecks_the_pair(client: AsyncClient):
    """Между показом списка и нажатием запись могли поправить: склеивать то,
    что парой уже не является, нельзя."""
    first = await _account(client, "Первый банк")
    second = await _account(client, "Второй банк")
    spent = await _out(client, first, "2026-02-27")
    received = await _in(client, second, "2026-02-27")
    await client.patch(f"/transactions/{received['id']}", json={"amount": "1300.00"})

    resp = await client.post(MATCHES + "/merge", json={"first_id": spent["id"], "second_id": received["id"]})
    assert resp.status_code == 409
    assert len(await _all_transactions(client)) == 2


async def test_form_check_finds_a_recorded_transfer(client: AsyncClient):
    """Идёт по выписке второго банка и заносит приход — форма заранее
    говорит, что этот перевод уже записан."""
    first = await _account(client, "Первый банк")
    second = await _account(client, "Второй банк")
    transfer = await _transfer(client, first, second, "2026-02-27")

    found = (
        await client.get(
            MATCHES + "/check",
            params={"type": "income", "account_id": second, "amount": "1206", "date": "2026-02-28"},
        )
    ).json()
    assert [(item["kind"], item["transaction"]["id"]) for item in found] == [
        ("transfer_and_in", transfer["id"])
    ]
    assert found[0]["transaction"]["account_name"] == "Первый банк"
    assert found[0]["transaction"]["transfer_account_name"] == "Второй банк"

    # Тот же перевод ещё раз — тоже.
    again = (
        await client.get(
            MATCHES + "/check",
            params={
                "type": "transfer",
                "account_id": first,
                "transfer_account_id": second,
                "amount": "1206.00",
                "date": "2026-02-27",
            },
        )
    ).json()
    assert [item["kind"] for item in again] == ["transfer_twice"]

    # А перевод обратно — нет.
    back = (
        await client.get(
            MATCHES + "/check",
            params={
                "type": "transfer",
                "account_id": second,
                "transfer_account_id": first,
                "amount": "1206.00",
                "date": "2026-02-27",
            },
        )
    ).json()
    assert back == []
