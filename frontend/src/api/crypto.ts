import { api } from "@/api/client";
import type {
  CryptoHistoryResponse,
  CryptoHolding,
  CryptoHoldingCreateInput,
  CryptoRange,
  CryptoSearchResult,
  CryptoSyncResult,
  CryptoTransaction,
  CryptoTransactionInput,
} from "@/types";

// Also triggers the lazy once-a-day auto-refresh server-side — see
// services/crypto_service.py.
export function fetchCryptoHoldings() {
  return api.get<CryptoSyncResult>("/crypto/holdings");
}

export function refreshCryptoPrices() {
  return api.post<CryptoSyncResult>("/crypto/refresh", {});
}

export function createCryptoHolding(input: CryptoHoldingCreateInput) {
  return api.post<CryptoHolding>("/crypto/holdings", input);
}

// Buy more of, or sell some of, a coin already being tracked.
export function addCryptoTransaction(assetId: number, input: CryptoTransactionInput) {
  return api.post<CryptoHolding>(`/crypto/holdings/${assetId}/transactions`, input);
}

export function fetchCryptoTransactions(assetId: number) {
  return api.get<CryptoTransaction[]>(`/crypto/holdings/${assetId}/transactions`);
}

export function updateCryptoTransaction(transactionId: number, input: CryptoTransactionInput) {
  return api.patch<CryptoHolding>(`/crypto/transactions/${transactionId}`, input);
}

export function deleteCryptoTransaction(transactionId: number) {
  return api.delete<void>(`/crypto/transactions/${transactionId}`);
}

// Reuses the existing asset-delete endpoint — deleting the Asset cascades
// to the linked crypto_holdings row (and its whole transaction log)
// server-side, no dedicated endpoint.
export function deleteCryptoHolding(assetId: number) {
  return api.delete<void>(`/assets/${assetId}`);
}

export function searchCryptoCoins(query: string) {
  return api.get<CryptoSearchResult[]>(`/crypto/search?q=${encodeURIComponent(query)}`);
}

export function fetchCryptoHistory(range: CryptoRange) {
  return api.get<CryptoHistoryResponse>(`/crypto/history?range=${range}`);
}
