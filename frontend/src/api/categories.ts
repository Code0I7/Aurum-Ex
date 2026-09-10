import { api } from "@/api/client";
import type { Category, CategoryInput, CategoryUpdateInput, CategoryTotal, CategoryUsage } from "@/types";

export function fetchCategories() {
  return api.get<Category[]>("/categories");
}

export function createCategory(input: CategoryInput) {
  return api.post<Category>("/categories", input);
}

export function updateCategory(id: number, input: CategoryUpdateInput) {
  return api.patch<Category>(`/categories/${id}`, input);
}

// Что зацепит удаление. Запрашивается по требованию, прямо перед
// вопросом: считать это для каждой из полутора сотен категорий на каждой
// загрузке списка незачем.
export function fetchCategoryUsage(id: number) {
  return api.get<CategoryUsage>(`/categories/${id}/usage`);
}

export function deleteCategory(id: number) {
  return api.delete<void>(`/categories/${id}`);
}

export function fetchCategoryTotals(startDate?: string, endDate?: string) {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const query = params.toString();
  return api.get<CategoryTotal[]>(`/categories/totals${query ? `?${query}` : ""}`);
}
