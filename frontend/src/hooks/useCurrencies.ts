import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addWatchedCurrency,
  backfillRates,
  fetchRateHistory,
  fetchRates,
  removeWatchedCurrency,
  syncRates,
} from "@/api/currencies";
import { invalidateMoneyQueries } from "@/lib/queryInvalidation";

export function useRates() {
  return useQuery({ queryKey: ["currency-rates"], queryFn: fetchRates });
}

/**
 * История курса за период. Запрос уходит, только когда валюта выбрана: окно
 * графика существует и закрытым, а спрашивать историю неизвестно чего
 * незачем.
 *
 * Загруженный ряд остаётся в кэше на время сеанса: курс прошедшего дня не
 * меняется, и перещёлкивание периодов туда-обратно не должно ходить в сеть
 * заново.
 */
export function useRateHistory(
  code: string | null,
  start: string,
  end: string,
  monthly: boolean
) {
  return useQuery({
    queryKey: ["currency-history", code, start, end, monthly],
    queryFn: () => fetchRateHistory(code as string, start, end, monthly),
    enabled: Boolean(code && start && end),
    staleTime: 10 * 60_000,
  });
}

/**
 * Загруженный курс меняет не только табличку с курсами.
 *
 * Тем же нажатием досчитываются операции, которые ждали именно его: у них
 * появляется сумма в валюте установки, и они возвращаются в капитал, в
 * расчёты с людьми, в отчёты. Обновлять один список курсов значило бы
 * оставить на экране прежние итоги — те самые, ради которых курс и грузили.
 */
function useInvalidateAfterRates() {
  const queryClient = useQueryClient();
  return () => invalidateMoneyQueries(queryClient);
}

export function useSyncRates() {
  const invalidate = useInvalidateAfterRates();
  return useMutation({ mutationFn: syncRates, onSuccess: invalidate });
}

export function useBackfillRates() {
  const invalidate = useInvalidateAfterRates();
  return useMutation({ mutationFn: backfillRates, onSuccess: invalidate });
}

/**
 * Список наблюдения итогов не меняет: это про то, на что человек хочет
 * смотреть, а не про его деньги. Поэтому обновляется только табличка
 * курсов — курс новой валюты появится со следующей загрузкой.
 */
function useInvalidateWatchlist() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["currency-rates"] });
}

export function useAddWatchedCurrency() {
  const invalidate = useInvalidateWatchlist();
  return useMutation({
    mutationFn: (code: string) => addWatchedCurrency(code),
    onSuccess: invalidate,
  });
}

export function useRemoveWatchedCurrency() {
  const invalidate = useInvalidateWatchlist();
  return useMutation({
    mutationFn: (code: string) => removeWatchedCurrency(code),
    onSuccess: invalidate,
  });
}
