"""Crypto holdings: creation, quantity updates, and the lazy/forced price
sync. CoinGecko itself is never called in tests —
services/crypto_service.py's _fetch_prices_batch is monkeypatched with a
canned price feed instead, same way any external dependency would be.
"""
from decimal import Decimal

import httpx
from httpx import AsyncClient

from app.services import crypto_service
from tests.helpers import money


async def _add_bitcoin(client: AsyncClient, quantity: str = "0.5") -> dict:
    resp = await client.post(
        "/crypto/holdings",
        json={"coingecko_id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "quantity": quantity},
    )
    assert resp.status_code == 201
    return resp.json()


def _fake_fetch(prices: dict[str, Decimal]):
    async def fetch(coingecko_ids, vs_currency):
        return {cid: prices[cid] for cid in coingecko_ids if cid in prices}

    return fetch


async def test_create_holding_seeds_todays_value_immediately(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_prices_batch", _fake_fetch({"bitcoin": Decimal("50000")}))

    holding = await _add_bitcoin(client, "0.5")

    assert holding["symbol"] == "BTC"  # normalized to uppercase
    assert money(holding["value"]) == money("25000")  # 0.5 * 50000
    assert money(holding["unit_price"]) == money("50000")


async def test_holding_shows_up_in_net_worth_breakdown(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_prices_batch", _fake_fetch({"bitcoin": Decimal("50000")}))
    await _add_bitcoin(client, "1")

    resp = await client.get("/net-worth/summary")

    breakdown = {item["key"]: item for item in resp.json()["breakdown"]}
    assert money(breakdown["crypto"]["amount"]) == money("50000")


async def test_update_quantity_recomputes_value_without_calling_coingecko(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_prices_batch", _fake_fetch({"bitcoin": Decimal("50000")}))
    holding = await _add_bitcoin(client, "0.5")

    async def fail_if_called(coingecko_ids, vs_currency):
        raise AssertionError("updating quantity must not call CoinGecko")

    monkeypatch.setattr(crypto_service, "_fetch_prices_batch", fail_if_called)

    resp = await client.patch(f"/crypto/holdings/{holding['asset_id']}", json={"quantity": "2"})

    assert resp.status_code == 200
    assert money(resp.json()["value"]) == money("100000")  # 2 * 50000 (last known price)


async def test_deleting_the_asset_removes_the_crypto_holding_too(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_prices_batch", _fake_fetch({"bitcoin": Decimal("50000")}))
    holding = await _add_bitcoin(client)

    resp = await client.delete(f"/assets/{holding['asset_id']}")
    assert resp.status_code == 204

    resp = await client.get("/crypto/holdings")
    assert resp.json()["holdings"] == []


async def test_get_holdings_does_not_resync_within_24_hours(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_prices_batch", _fake_fetch({"bitcoin": Decimal("50000")}))
    await _add_bitcoin(client)

    calls: list[list[str]] = []

    async def counting_fetch(coingecko_ids, vs_currency):
        calls.append(coingecko_ids)
        return {}

    monkeypatch.setattr(crypto_service, "_fetch_prices_batch", counting_fetch)

    resp = await client.get("/crypto/holdings")

    assert resp.json()["synced"] is False
    assert calls == []  # creation's own sync already satisfied the 24h window


async def test_manual_refresh_button_bypasses_the_24h_window(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_prices_batch", _fake_fetch({"bitcoin": Decimal("50000")}))
    await _add_bitcoin(client)

    calls: list[list[str]] = []

    async def counting_fetch(coingecko_ids, vs_currency):
        calls.append(coingecko_ids)
        return {"bitcoin": Decimal("60000")}

    monkeypatch.setattr(crypto_service, "_fetch_prices_batch", counting_fetch)

    resp = await client.post("/crypto/refresh")

    assert resp.json()["synced"] is True
    assert calls == [["bitcoin"]]
    assert money(resp.json()["holdings"][0]["value"]) == money("30000")  # 0.5 * 60000


async def test_coingecko_outage_keeps_last_known_value_instead_of_failing(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(crypto_service, "_fetch_prices_batch", _fake_fetch({"bitcoin": Decimal("50000")}))
    await _add_bitcoin(client)

    async def broken_fetch(coingecko_ids, vs_currency):
        raise httpx.ConnectError("simulated outage")

    monkeypatch.setattr(crypto_service, "_fetch_prices_batch", broken_fetch)

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
        json={"coingecko_id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "quantity": "0.5"},
    )

    assert resp.status_code == 400


async def test_backup_roundtrip_preserves_the_holding_not_just_the_asset(client: AsyncClient, monkeypatch):
    """A crypto holding is an Asset underneath, so it would still show up
    after a restore even without this — but as an inert manual asset,
    having silently lost which coin it was and how much was held. Backup
    must carry the CryptoHolding row too, not just Asset/AssetValuation."""
    monkeypatch.setattr(crypto_service, "_fetch_prices_batch", _fake_fetch({"bitcoin": Decimal("50000")}))
    holding = await _add_bitcoin(client, "0.5")

    payload = (await client.get("/backup/export")).json()
    assert len(payload["crypto_holdings"]) == 1
    backed_up = payload["crypto_holdings"][0]
    assert backed_up["asset_id"] == holding["asset_id"]
    assert backed_up["coingecko_id"] == "bitcoin"
    assert backed_up["symbol"] == "BTC"
    assert backed_up["name"] == "Bitcoin"
    assert backed_up["thumb_url"] is None
    assert money(backed_up["quantity"]) == money("0.5")

    import_resp = await client.post("/backup/import", json=payload)
    assert import_resp.status_code == 200, import_resp.text

    resp = await client.get("/crypto/holdings")
    restored = resp.json()["holdings"]
    assert len(restored) == 1
    assert restored[0]["coingecko_id"] == "bitcoin"
    assert restored[0]["asset_id"] == holding["asset_id"]
    assert money(restored[0]["value"]) == money("25000")  # AssetValuation history survives too
