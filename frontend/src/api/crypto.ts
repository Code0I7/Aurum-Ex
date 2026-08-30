import { api } from "@/api/client";
import type { CryptoHolding, CryptoHoldingInput, CryptoSearchResult, CryptoSyncResult } from "@/types";

// Also triggers the lazy once-a-day auto-refresh server-side — see
// services/crypto_service.py.
export function fetchCryptoHoldings() {
  return api.get<CryptoSyncResult>("/crypto/holdings");
}

export function refreshCryptoPrices() {
  return api.post<CryptoSyncResult>("/crypto/refresh", {});
}

export function createCryptoHolding(input: CryptoHoldingInput) {
  return api.post<CryptoHolding>("/crypto/holdings", input);
}

export function updateCryptoHoldingQuantity(assetId: number, quantity: string) {
  return api.patch<CryptoHolding>(`/crypto/holdings/${assetId}`, { quantity });
}

// Reuses the existing asset-delete endpoint — deleting the Asset cascades
// to the linked crypto_holdings row server-side, no dedicated endpoint.
export function deleteCryptoHolding(assetId: number) {
  return api.delete<void>(`/assets/${assetId}`);
}

export function searchCryptoCoins(query: string) {
  return api.get<CryptoSearchResult[]>(`/crypto/search?q=${encodeURIComponent(query)}`);
}
