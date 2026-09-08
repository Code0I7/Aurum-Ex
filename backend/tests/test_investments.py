"""Инвестиции через API: портфели, позиции, сделки, FIFO.

Арифметика FIFO проверена отдельно и без базы (tests/test_fifo.py). Здесь —
то, что можно сломать только на стыке: порядок сделок внутри дня, пересчёт
после правки, разнесение продаж по партиям в ответе.
"""
from decimal import Decimal

from httpx import AsyncClient


async def _portfolio(client: AsyncClient, name: str = "Долгосрок") -> dict:
    resp = await client.post("/investments/portfolios", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _holding(client: AsyncClient, portfolio_id: int, name: str = "ACME", kind: str = "stock") -> dict:
    resp = await client.post(
        "/investments/holdings",
        json={"portfolio_id": portfolio_id, "name": name, "ticker": name, "kind": kind, "currency": "RUB"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _trade(
    client: AsyncClient,
    holding_id: int,
    side: str,
    quantity: str,
    price: str,
    date: str,
    fee: str = "0",
) -> dict:
    resp = await client.post(
        f"/investments/holdings/{holding_id}/trades",
        json={
            "side": side,
            "quantity": quantity,
            "price_per_unit": price,
            "fee": fee,
            "trade_date": date,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_the_paper_example_holds_through_the_api(client: AsyncClient):
    """Тот же расчёт, что в документации к модели: 1 по 500, 5 по 100,
    продажа 2 по 150 даёт убыток 300, а не 33."""
    portfolio = await _portfolio(client)
    holding = await _holding(client, portfolio["id"])

    await _trade(client, holding["id"], "buy", "1", "500", "2026-01-10")
    await _trade(client, holding["id"], "buy", "5", "100", "2026-02-10")
    position = await _trade(client, holding["id"], "sell", "2", "150", "2026-03-10")

    assert Decimal(position["realised"]) == Decimal("-300")
    assert Decimal(position["quantity"]) == Decimal("4")
    assert Decimal(position["cost_basis"]) == Decimal("400")
    assert Decimal(position["average_cost"]) == Decimal("100")


async def test_two_trades_on_one_day_keep_their_entry_order(client: AsyncClient):
    """Две сделки одной датой не должны меняться местами между загрузками:
    иначе зафиксированная прибыль менялась бы при обновлении страницы."""
    portfolio = await _portfolio(client)
    holding = await _holding(client, portfolio["id"])

    await _trade(client, holding["id"], "buy", "1", "500", "2026-01-10")
    await _trade(client, holding["id"], "buy", "5", "100", "2026-01-10")
    await _trade(client, holding["id"], "sell", "2", "150", "2026-01-10")

    for _ in range(3):
        detail = (await client.get(f"/investments/holdings/{holding['id']}")).json()
        assert Decimal(detail["realised"]) == Decimal("-300")


async def test_disposals_say_which_lots_were_sold(client: AsyncClient):
    """«Продали то, что купили в мае 2022-го» — ответ, который
    средневзвешенная дать не могла в принципе."""
    portfolio = await _portfolio(client)
    holding = await _holding(client, portfolio["id"])

    await _trade(client, holding["id"], "buy", "3", "10", "2022-05-01")
    await _trade(client, holding["id"], "buy", "3", "20", "2023-05-01")
    await _trade(client, holding["id"], "sell", "5", "50", "2026-01-01")

    detail = (await client.get(f"/investments/holdings/{holding['id']}")).json()
    disposal = detail["disposals"][0]
    assert Decimal(disposal["cost"]) == Decimal("70")
    assert Decimal(disposal["realised"]) == Decimal("180")
    assert [(Decimal(lot["quantity"]), lot["acquired_on"]) for lot in disposal["lots"]] == [
        (Decimal("3"), "2022-05-01"),
        (Decimal("2"), "2023-05-01"),
    ]
    # Осталась одна штука по 20 — открытая партия видна отдельно.
    assert len(detail["open_lots"]) == 1
    assert Decimal(detail["open_lots"][0]["quantity"]) == Decimal("1")


async def test_fees_are_part_of_the_cost_and_of_the_proceeds(client: AsyncClient):
    portfolio = await _portfolio(client)
    holding = await _holding(client, portfolio["id"])

    await _trade(client, holding["id"], "buy", "10", "100", "2026-01-10", fee="50")
    position = (await client.get(f"/investments/holdings/{holding['id']}")).json()
    assert Decimal(position["cost_basis"]) == Decimal("1050")

    position = await _trade(client, holding["id"], "sell", "10", "120", "2026-02-10", fee="30")
    # 1200 − 30 = 1170 выручки против 1050 стоимости.
    assert Decimal(position["realised"]) == Decimal("120")


async def test_value_is_unknown_until_a_price_is_set(client: AsyncClient):
    """Ноль означал бы, что актив обесценился, а он просто не переоценён."""
    portfolio = await _portfolio(client)
    holding = await _holding(client, portfolio["id"])
    await _trade(client, holding["id"], "buy", "10", "100", "2026-01-10")

    position = (await client.get(f"/investments/holdings/{holding['id']}")).json()
    assert position["value"] is None
    assert position["unrealised"] is None

    await client.patch(f"/investments/holdings/{holding['id']}", json={"last_price": "150"})
    position = (await client.get(f"/investments/holdings/{holding['id']}")).json()
    assert Decimal(position["value"]) == Decimal("1500")
    assert Decimal(position["unrealised"]) == Decimal("500")
    assert position["unrealised_percent"] == 50.0
    # Ручная переоценка ставит отметку времени: цена без даты не даёт понять,
    # вчерашняя она или двухлетней давности.
    assert position["last_price_at"] is not None


async def test_editing_a_trade_recomputes_the_position(client: AsyncClient):
    """Хранимый итог был бы вторым источником истины и разошёлся бы с
    журналом при первой же правке."""
    portfolio = await _portfolio(client)
    holding = await _holding(client, portfolio["id"])
    await _trade(client, holding["id"], "buy", "10", "100", "2026-01-10")

    trades = (await client.get(f"/investments/holdings/{holding['id']}/trades")).json()
    resp = await client.patch(f"/investments/trades/{trades[0]['id']}", json={"price_per_unit": "200"})
    assert resp.status_code == 200, resp.text
    assert Decimal(resp.json()["cost_basis"]) == Decimal("2000")

    resp = await client.delete(f"/investments/trades/{trades[0]['id']}")
    assert Decimal(resp.json()["quantity"]) == Decimal("0")


async def test_selling_more_than_held_is_surfaced(client: AsyncClient):
    """Не ошибка расчёта, а пропуск в данных: забытая покупка или неверная
    дата. Прятать её нельзя."""
    portfolio = await _portfolio(client)
    holding = await _holding(client, portfolio["id"])
    await _trade(client, holding["id"], "buy", "2", "100", "2026-01-10")
    position = await _trade(client, holding["id"], "sell", "5", "150", "2026-02-10")

    assert Decimal(position["oversold"]) == Decimal("3")
    assert Decimal(position["quantity"]) == Decimal("0")


async def test_crypto_and_stocks_share_one_engine(client: AsyncClient):
    """Партии и списание одинаковы для акции и для монеты — вкладка это
    фильтр, а не отдельная система."""
    portfolio = await _portfolio(client)
    stock = await _holding(client, portfolio["id"], "ACME", "stock")
    coin = await _holding(client, portfolio["id"], "BTC", "crypto")

    for holding_id in (stock["id"], coin["id"]):
        await _trade(client, holding_id, "buy", "1", "500", "2026-01-10")
        await _trade(client, holding_id, "buy", "5", "100", "2026-02-10")
        await _trade(client, holding_id, "sell", "2", "150", "2026-03-10")

    holdings = {row["name"]: row for row in (await client.get("/investments/holdings")).json()}
    assert Decimal(holdings["ACME"]["realised"]) == Decimal("-300")
    assert Decimal(holdings["BTC"]["realised"]) == Decimal("-300")


async def test_fractional_crypto_quantities_survive_a_round_trip(client: AsyncClient):
    portfolio = await _portfolio(client)
    holding = await _holding(client, portfolio["id"], "BTC", "crypto")
    await _trade(client, holding["id"], "buy", "0.00000001", "5000000", "2026-01-10")
    await _trade(client, holding["id"], "buy", "0.5", "4000000", "2026-02-10")

    position = (await client.get(f"/investments/holdings/{holding['id']}")).json()
    assert Decimal(position["quantity"]) == Decimal("0.50000001")
    assert Decimal(position["cost_basis"]) == Decimal("2000000.05")


async def test_portfolio_totals_add_up_its_holdings(client: AsyncClient):
    portfolio = await _portfolio(client)
    first = await _holding(client, portfolio["id"], "ACME")
    second = await _holding(client, portfolio["id"], "GAZP")
    await _trade(client, first["id"], "buy", "10", "100", "2026-01-10")
    await _trade(client, second["id"], "buy", "5", "200", "2026-01-10")
    await client.patch(f"/investments/holdings/{first['id']}", json={"last_price": "150"})

    row = next(item for item in (await client.get("/investments/portfolios")).json() if item["id"] == portfolio["id"])
    assert row["holdings"] == 2
    assert Decimal(row["cost_basis"]) == Decimal("2000")
    # Стоимость считает только то, у чего есть цена: у второй позиции её нет.
    assert Decimal(row["value"]) == Decimal("1500")


async def test_a_portfolio_with_holdings_cannot_be_deleted(client: AsyncClient):
    """Удаление унесло бы позиции вместе с журналом сделок."""
    portfolio = await _portfolio(client)
    await _holding(client, portfolio["id"])

    resp = await client.delete(f"/investments/portfolios/{portfolio['id']}")
    assert resp.status_code == 400


async def test_holdings_are_listed_by_money_put_in(client: AsyncClient):
    """Позиция, выросшая втрое, не важнее той, в которую вложено втрое
    больше: список отвечает на вопрос «где мои деньги»."""
    portfolio = await _portfolio(client)
    small = await _holding(client, portfolio["id"], "AAA")
    big = await _holding(client, portfolio["id"], "BBB")
    await _trade(client, small["id"], "buy", "1", "100", "2026-01-10")
    await _trade(client, big["id"], "buy", "1", "5000", "2026-01-10")
    await client.patch(f"/investments/holdings/{small['id']}", json={"last_price": "100000"})

    names = [row["name"] for row in (await client.get("/investments/holdings")).json()]
    assert names == ["BBB", "AAA"]
