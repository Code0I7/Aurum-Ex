import { api } from "@/api/client";
import type {
  BackfillResult,
  CurrencyRate,
  RateHistory,
  RateSyncResult,
  WatchedCurrency,
} from "@/types";

/** Курсы валют, за которыми следят, плюс те, что нужны расчётам. */
export function fetchRates() {
  return api.get<CurrencyRate[]>("/currencies/rates");
}

/**
 * История курса одной валюты за период.
 *
 * Недостающие дни догружает сам сервер при этом же запросе: держать всю
 * историю всех валют на всякий случай незачем, а спросить её у ЦБ за раз —
 * одно обращение на валюту.
 */
export function fetchRateHistory(code: string, start: string, end: string, monthly: boolean) {
  const query = new URLSearchParams({ start_date: start, end_date: end, monthly: String(monthly) });
  return api.get<RateHistory>(`/currencies/${code}/history?${query.toString()}`);
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
