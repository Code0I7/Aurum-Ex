"""Crypto holdings: buy/sell transaction log, weighted-average cost basis,
and the lazy/forced price sync. CoinGecko itself is never called in tests —
services/crypto_service.py's _fetch_market_data is monkeypatched with a
canned market-data feed instead, same way any external dependency would be.
"""
from decimal import Decimal

import httpx
from httpx import AsyncClient

from app.services import crypto_service
from tests.helpers import money


def _point(price: str, change_1h: str | None = None, change_24h: str | None = None, change_7d: str | None = None):
    return crypto_service._MarketPoint(
        price=Decimal(price),
        change_1h=Decimal(change_1h) if change_1h else None,
        change_24h=Decimal(change_24h) if change_24h else None,
        change_7d=Decimal(change_7d) if change_7d else None,
    )


def _fake_fetch(prices: dict[str, "crypto_service._MarketPoint"]):
    async def fetch(coingecko_ids, vs_currency):
        return {cid: prices[cid] for cid in coingecko_ids if cid in prices}

    return fetch


async def _add_bitcoin(client: AsyncClient, quantity: str = "0.5", price_per_unit: str = "40000") -> dict:
    resp = await client.post(
        "/crypto/holdings",
        json={
            "coingecko_id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "quantity": quantity,
            "price_per_unit": price_per_unit,
            "date": "2026-01-01",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_holding_seeds_todays_value_and_position_immediately(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))

    holding = await _add_bitcoin(client, "0.5", "40000")

    assert holding["symbol"] == "BTC"  # normalized to uppercase
    assert money(holding["quantity"]) == money("0.5")
    assert money(holding["avg_buy_price"]) == money("40000")
    assert money(holding["current_price"]) == money("50000")
    assert money(holding["value"]) == money("25000")  # 0.5 * 50000
    assert money(holding["cost_basis"]) == money("20000")  # 0.5 * 40000
    assert money(holding["profit_loss"]) == money("5000")
    assert round(holding["profit_loss_percent"], 2) == 25.0


async def test_holding_shows_up_in_net_worth_breakdown(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    await _add_bitcoin(client, "1", "40000")

    resp = await client.get("/net-worth/summary")

    breakdown = {item["key"]: item for item in resp.json()["breakdown"]}
    assert money(breakdown["crypto"]["amount"]) == money("50000")


async def test_second_buy_blends_into_weighted_average_cost(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "1", "40000")  # cost basis: 40000

    async def fail_if_called(coingecko_ids, vs_currency):
        raise AssertionError("adding a transaction must not call CoinGecko")

    monkeypatch.setattr(crypto_service, "_fetch_market_data", fail_if_called)

    resp = await client.post(
        f"/crypto/holdings/{holding['asset_id']}/transactions",
        json={"type": "buy", "quantity": "1", "price_per_unit": "60000", "date": "2026-02-01"},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert money(body["quantity"]) == money("2")
    # (1*40000 + 1*60000) / 2 = 50000
    assert money(body["avg_buy_price"]) == money("50000")
    assert money(body["value"]) == money("100000")  # 2 * 50000 (last known price, unchanged)


async def test_sell_reduces_quantity_but_not_the_average_cost_of_what_remains(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "2", "40000")  # avg cost 40000

    resp = await client.post(
        f"/crypto/holdings/{holding['asset_id']}/transactions",
        json={"type": "sell", "quantity": "1", "price_per_unit": "55000", "date": "2026-02-01"},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert money(body["quantity"]) == money("1")
    assert money(body["avg_buy_price"]) == money("40000")  # unchanged by the sell
    assert money(body["value"]) == money("50000")  # 1 * 50000


async def test_selling_more_than_held_is_rejected(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "1", "40000")

    resp = await client.post(
        f"/crypto/holdings/{holding['asset_id']}/transactions",
        json={"type": "sell", "quantity": "2", "price_per_unit": "55000", "date": "2026-02-01"},
    )

    assert resp.status_code == 400


async def test_deleting_a_transaction_recomputes_the_position(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "1", "40000")

    second = await client.post(
        f"/crypto/holdings/{holding['asset_id']}/transactions",
        json={"type": "buy", "quantity": "1", "price_per_unit": "60000", "date": "2026-02-01"},
    )
    tx_id = next(
        t["id"]
        for t in (await client.get(f"/crypto/holdings/{holding['asset_id']}/transactions")).json()
        if t["price_per_unit"] == "60000.000000000000000000"
    )
    assert second.json()["quantity"] == "2.000000000000000000"

    resp = await client.delete(f"/crypto/transactions/{tx_id}")
    assert resp.status_code == 204

    refreshed = (await client.get("/crypto/holdings")).json()["holdings"][0]
    assert money(refreshed["quantity"]) == money("1")
    assert money(refreshed["avg_buy_price"]) == money("40000")


async def test_transaction_history_lists_newest_first(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "1", "40000", )
    await client.post(
        f"/crypto/holdings/{holding['asset_id']}/transactions",
        json={"type": "buy", "quantity": "1", "price_per_unit": "60000", "date": "2026-02-01"},
    )

    resp = await client.get(f"/crypto/holdings/{holding['asset_id']}/transactions")

    assert resp.status_code == 200
    dates = [t["date"] for t in resp.json()]
    assert dates == ["2026-02-01", "2026-01-01"]


async def test_deleting_the_asset_removes_the_crypto_holding_too(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client)

    resp = await client.delete(f"/assets/{holding['asset_id']}")
    assert resp.status_code == 204

    resp = await client.get("/crypto/holdings")
    assert resp.json()["holdings"] == []


async def test_get_holdings_does_not_resync_within_24_hours(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    await _add_bitcoin(client)

    calls: list[list[str]] = []

    async def counting_fetch(coingecko_ids, vs_currency):
        calls.append(coingecko_ids)
        return {}

    monkeypatch.setattr(crypto_service, "_fetch_market_data", counting_fetch)

    resp = await client.get("/crypto/holdings")

    assert resp.json()["synced"] is False
    assert calls == []  # creation's own sync already satisfied the 24h window


async def test_manual_refresh_button_bypasses_the_24h_window_and_updates_changes(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    await _add_bitcoin(client, "0.5", "40000")

    calls: list[list[str]] = []

    async def counting_fetch(coingecko_ids, vs_currency):
        calls.append(coingecko_ids)
        return {"bitcoin": _point("60000", change_1h="0.5", change_24h="2.1", change_7d="-3.4")}

    monkeypatch.setattr(crypto_service, "_fetch_market_data", counting_fetch)

    resp = await client.post("/crypto/refresh")

    assert resp.json()["synced"] is True
    assert calls == [["bitcoin"]]
    holding = resp.json()["holdings"][0]
    assert money(holding["value"]) == money("30000")  # 0.5 * 60000
    assert money(holding["price_change_1h"]) == money("0.5")
    assert money(holding["price_change_24h"]) == money("2.1")
    assert money(holding["price_change_7d"]) == money("-3.4")


async def test_coingecko_outage_keeps_last_known_value_instead_of_failing(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    await _add_bitcoin(client, "0.5", "40000")

    async def broken_fetch(coingecko_ids, vs_currency):
        raise httpx.ConnectError("simulated outage")

    monkeypatch.setattr(crypto_service, "_fetch_market_data", broken_fetch)

    resp = await client.post("/crypto/refresh")

    assert resp.status_code == 200
    body = resp.json()
    assert body["synced"] is False
    assert body["error_key"] == "unreachable"
    assert money(body["holdings"][0]["value"]) == money("25000")  # unchanged from creation


async def test_create_rejects_when_no_api_key_configured(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service.get_settings(), "coingecko_api_key", "")

    resp = await client.post(
        "/crypto/holdings",
        json={
            "coingecko_id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "quantity": "0.5",
            "price_per_unit": "40000",
            "date": "2026-01-01",
        },
    )

    assert resp.status_code == 400


async def test_backup_roundtrip_preserves_holding_and_transaction_log(client: AsyncClient, monkeypatch):
    """A crypto holding is an Asset underneath, so it would still show up
    after a restore even without this — but as an inert manual asset,
    having silently lost which coin it was and its whole buy/sell history
    (so quantity and avg buy price couldn't be recomputed). Backup must
    carry both CryptoHolding and CryptoTransaction rows."""
    monkeypatch.setattr(crypto_service, "_fetch_market_data", _fake_fetch({"bitcoin": _point("50000")}))
    holding = await _add_bitcoin(client, "1", "40000")
    await client.post(
        f"/crypto/holdings/{holding['asset_id']}/transactions",
        json={"type": "buy", "quantity": "1", "price_per_unit": "60000", "date": "2026-02-01"},
    )

    payload = (await client.get("/backup/export")).json()
    assert len(payload["crypto_holdings"]) == 1
    assert len(payload["crypto_transactions"]) == 2

    import_resp = await client.post("/backup/import", json=payload)
    assert import_resp.status_code == 200, import_resp.text

    restored = (await client.get("/crypto/holdings")).json()["holdings"][0]
    assert restored["coingecko_id"] == "bitcoin"
    assert restored["asset_id"] == holding["asset_id"]
    assert money(restored["quantity"]) == money("2")
    assert money(restored["avg_buy_price"]) == money("50000")
    assert money(restored["value"]) == money("100000")  # last_price survived too (2 * 50000)
