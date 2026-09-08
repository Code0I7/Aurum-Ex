import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createCategory,
  deleteCategory,
  fetchCategories,
  fetchCategoryTotals,
  updateCategory,
} from "@/api/categories";
import type { CategoryInput, CategoryUpdateInput } from "@/types";

export function useCategories() {
  return useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
}

// Category name/color/icon are denormalized into several read models
// (transactions, dashboard, reports, budgets, recurring templates) — any
// create/update/delete has to refresh all of them, same set an account
// mutation invalidates in useAccounts.ts.
function invalidateCategoryConsumers(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["categories"] });
  queryClient.invalidateQueries({ queryKey: ["transactions"] });
  queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
  queryClient.invalidateQueries({ queryKey: ["category-spending-report"] });
  queryClient.invalidateQueries({ queryKey: ["category-ranking"] });
  queryClient.invalidateQueries({ queryKey: ["budgets"] });
  queryClient.invalidateQueries({ queryKey: ["budget-status"] });
  queryClient.invalidateQueries({ queryKey: ["recurring"] });
}

export function useCreateCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CategoryInput) => createCategory(input),
    onSuccess: () => invalidateCategoryConsumers(queryClient),
  });
}

export function useUpdateCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: CategoryUpdateInput }) => updateCategory(id, input),
    onSuccess: () => invalidateCategoryConsumers(queryClient),
  });
}

export function useDeleteCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteCategory(id),
    onSuccess: () => invalidateCategoryConsumers(queryClient),
  });
}

// Суммы по категориям. Без периода — за всё время: список категорий
// открывают, чтобы разобраться в накопившемся, а не посмотреть текущий месяц.
export function useCategoryTotals(startDate?: string, endDate?: string) {
  return useQuery({
    queryKey: ["categories", "totals", startDate ?? null, endDate ?? null],
    queryFn: () => fetchCategoryTotals(startDate, endDate),
  });
}
