import { api } from "@/api/client";
import type { BackfillResult, CurrencyRate, RateSyncResult, WatchedCurrency } from "@/types";

/** Курсы валют, за которыми следят, плюс те, что нужны расчётам. */
export function fetchRates() {
  return api.get<CurrencyRate[]>("/currencies/rates");
}

export function addWatchedCurrency(code: string) {
  return api.post<WatchedCurrency>("/currencies", { code });
}

export function removeWatchedCurrency(code: string) {
  return api.delete<void>(`/currencies/${code}`);
}

/** Загрузка курсов на сегодня с сайта ЦБ. */
export function syncRates() {
  return api.post<RateSyncResult>("/currencies/rates/sync", {});
}

/** Добор курсов за прошедшие даты, на которые их не хватило. */
export function backfillRates() {
  return api.post<BackfillResult>("/currencies/rates/backfill", {});
}
