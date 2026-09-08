import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  bulkCreateTransactions,
  createTransaction,
  deleteTransaction,
  fetchTransactions,
  fetchTransactionYears,
  updateTransaction,
  type TransactionFilters,
} from "@/api/transactions";
import { api } from "@/api/client";
import type { Transaction, TransactionInput } from "@/types";

function useInvalidateAfterTransactionChange() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
    queryClient.invalidateQueries({ queryKey: ["transaction-years"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    queryClient.invalidateQueries({ queryKey: ["net-worth-summary"] });
    queryClient.invalidateQueries({ queryKey: ["category-spending-report"] });
    queryClient.invalidateQueries({ queryKey: ["category-ranking"] });
    queryClient.invalidateQueries({ queryKey: ["budget-status"] });
    queryClient.invalidateQueries({ queryKey: ["financial-alerts"] });
    queryClient.invalidateQueries({ queryKey: ["advice"] });
    queryClient.invalidateQueries({ queryKey: ["cash-flow"] });
  };
}

export function useTransactions(filters: TransactionFilters, enabled = true) {
  return useQuery({
    queryKey: ["transactions", filters],
    queryFn: () => fetchTransactions(filters),
    // Выключается, когда список показывается лентой: незачем держать
    // постраничный запрос живым, пока он никому не нужен.
    enabled,
  });
}

/**
 * Тот же список, но лентой: страница подгружается кнопкой «Загрузить ещё», а
 * не заменяет предыдущую.
 *
 * Оба режима живут рядом намеренно. Страницы предсказуемы и не растут в
 * памяти — на четырёх годах истории это важно. Лента удобнее, когда листаешь
 * подряд и не хочешь терять из виду начало месяца. Выбор оставлен человеку,
 * потому что верного ответа для всех случаев тут нет.
 */
export function useInfiniteTransactions(filters: TransactionFilters, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: ["transactions", "feed", filters],
    queryFn: ({ pageParam }) => fetchTransactions({ ...filters, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((sum, page) => sum + page.items.length, 0);
      // Следующей страницы нет, когда загружено всё. Считаем по фактически
      // полученным строкам, а не по номеру страницы: между запросами записи
      // могли добавиться или исчезнуть.
      return loaded < lastPage.total ? allPages.length + 1 : undefined;
    },
    enabled,
    // Страницы ленты накапливаются, и держать их свежими по отдельности
    // незачем: список всё равно перезапрашивается целиком после любой правки.
    staleTime: 30_000,
  });
}

export function useTransactionYears() {
  return useQuery({
    queryKey: ["transaction-years"],
    queryFn: fetchTransactionYears,
  });
}

export function useCreateTransaction() {
  const invalidate = useInvalidateAfterTransactionChange();
  return useMutation({
    mutationFn: (input: TransactionInput) => createTransaction(input),
    onSuccess: invalidate,
  });
}

export function useUpdateTransaction() {
  const invalidate = useInvalidateAfterTransactionChange();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: Partial<TransactionInput> }) =>
      updateTransaction(id, input),
    onSuccess: invalidate,
  });
}

export function useBulkCreateTransactions() {
  const invalidate = useInvalidateAfterTransactionChange();
  return useMutation({
    mutationFn: (items: TransactionInput[]) => bulkCreateTransactions(items),
    onSuccess: invalidate,
  });
}

/** Перестановка операции внутри её дня. Инвалидирует те же запросы, что и
 * правка: порядок меняет баланс после операции, а значит и всё, что от него
 * считается. */
export function useReorderTransaction() {
  const invalidate = useInvalidateAfterTransactionChange();
  return useMutation({
    mutationFn: ({ id, position }: { id: number; position: number }) =>
      api.post<Transaction>(`/transactions/${id}/reorder`, { position }),
    onSuccess: invalidate,
  });
}

export function useDeleteTransaction() {
  const invalidate = useInvalidateAfterTransactionChange();
  return useMutation({
    mutationFn: (id: number) => deleteTransaction(id),
    onSuccess: invalidate,
  });
}
