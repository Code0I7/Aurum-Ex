import { api } from "@/api/client";
import type {
  CreditSummary,
  CreditTerms,
  CreditTermsInput,
  Settlement,
  SettlementSummary,
  TransitPerson,
  TransitSummary,
} from "@/types";

export function fetchSettlements() {
  return api.get<Settlement[]>("/settlements");
}

export function fetchSettlementSummary() {
  return api.get<SettlementSummary>("/settlements/summary");
}

// Транзит по людям за период. Год и месяц необязательны: без них отвечает
// на вопрос «с кем не сошлось вообще», с ними — «что было в этом месяце».
export function fetchTransitByPerson(year?: number, month?: number) {
  const params = new URLSearchParams();
  if (year !== undefined) params.set("year", String(year));
  if (month !== undefined) params.set("month", String(month));
  const query = params.toString();
  return api.get<TransitPerson[]>(`/settlements/transit-by-person${query ? `?${query}` : ""}`);
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
