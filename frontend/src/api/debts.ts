import { api } from "@/api/client";
import type {
  CreditSummary,
  CreditTerms,
  CreditTermsInput,
  Settlement,
  SettlementSummary,
  TransitSummary,
} from "@/types";

export function fetchSettlements() {
  return api.get<Settlement[]>("/settlements");
}

export function fetchSettlementSummary() {
  return api.get<SettlementSummary>("/settlements/summary");
}

export function fetchTransitSummary() {
  return api.get<TransitSummary>("/settlements/transit");
}

export function fetchCredits() {
  return api.get<CreditTerms[]>("/credits");
}

export function fetchCreditSummary() {
  return api.get<CreditSummary>("/credits/summary");
}

// Один вызов и на создание, и на правку: условия у счёта либо есть, либо
// нет — промежуточного состояния, которое различало бы POST и PATCH, не
// существует.
export function saveCreditTerms(accountId: number, input: CreditTermsInput) {
  return api.put<CreditTerms>(`/accounts/${accountId}/credit-terms`, input);
}

export function deleteCreditTerms(accountId: number) {
  return api.delete<void>(`/accounts/${accountId}/credit-terms`);
}
