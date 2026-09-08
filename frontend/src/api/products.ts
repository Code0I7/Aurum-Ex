import { api } from "@/api/client";
import type { Product, ProductInput, ProductPriceHistory, Unit } from "@/types";

export function fetchProducts(includeArchived = false) {
  return api.get<Product[]>(`/products${includeArchived ? "?include_archived=true" : ""}`);
}

// Подсказка при вводе позиции: ищет и по названию, и по штрихкоду — если
// товар отсканировали, в поле окажется код, а не слово.
export function suggestProducts(query: string) {
  return api.get<Product[]>(`/products/suggest?q=${encodeURIComponent(query)}`);
}

export function fetchPriceHistory(productId: number) {
  return api.get<ProductPriceHistory>(`/products/${productId}/prices`);
}

export function createProduct(input: ProductInput) {
  return api.post<Product>("/products", input);
}

export function updateProduct(id: number, input: Partial<ProductInput>) {
  return api.patch<Product>(`/products/${id}`, input);
}

export function deleteProduct(id: number) {
  return api.delete<void>(`/products/${id}`);
}

export function fetchUnits() {
  return api.get<Unit[]>("/units");
}
