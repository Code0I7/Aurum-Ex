import { api } from "@/api/client";
import type {
  SimilarTransaction,
  Transaction,
  TransactionInput,
  TransactionPage,
  TransactionType,
} from "@/types";

export type TransactionSort = "date_desc" | "amount_desc" | "amount_asc";

export interface TransactionFilters {
  year?: number;
  month?: number;
  start_date?: string;
  end_date?: string;
  account_id?: number;
  category_id?: number;
  tag_id?: number;
  type?: string;
  // Новые измерения Aurum-Ex.
  participant_id?: number;
  store_id?: number;
  counterparty_id?: number;
  include_excluded?: boolean;
  search?: string;
  sort?: TransactionSort;
  page?: number;
  page_size?: number;
}

export function fetchTransactions(filters: TransactionFilters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null) params.set(key, String(value));
  });
  return api.get<TransactionPage>(`/transactions?${params.toString()}`);
}

/** Full range of years to offer in the year picker, from the earliest
 * transaction through the current year (see backend for the "gap year"
 * rationale). */
export function fetchTransactionYears() {
  return api.get<number[]>("/transactions/years");
}

/**
 * Есть ли уже такая операция в этом дне.
 *
 * Спрашивается перед записью, а не проверяется при ней: отказ на самой
 * записи задел бы и импорт таблицы, и проведение регулярных платежей, где
 * повторы законны. Переспрашивать имеет смысл у того, кто вводит руками.
 */
export function fetchSimilarTransactions(params: {
  date: string;
  type: TransactionType;
  amount: string;
  description: string;
  category_id?: number | null;
}) {
  const query = new URLSearchParams({
    date: params.date,
    type: params.type,
    amount: params.amount,
    description: params.description,
  });
  if (params.category_id) query.set("category_id", String(params.category_id));
  return api.get<SimilarTransaction[]>(`/transactions/similar?${query.toString()}`);
}

export function createTransaction(input: TransactionInput) {
  return api.post<Transaction>("/transactions", input);
}

/** CSV import — see pages/CsvImportPage.tsx. All-or-nothing on the backend:
 * either every row is created, or (on a validation error) none are. */
export function bulkCreateTransactions(items: TransactionInput[]) {
  return api.post<{ created: number }>("/transactions/bulk", { items });
}

export function updateTransaction(id: number, input: Partial<TransactionInput>) {
  return api.patch<Transaction>(`/transactions/${id}`, input);
}

export function deleteTransaction(id: number) {
  return api.delete<void>(`/transactions/${id}`);
}
