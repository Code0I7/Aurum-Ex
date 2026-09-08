import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createProduct,
  deleteProduct,
  fetchPriceHistory,
  fetchProducts,
  fetchUnits,
  updateProduct,
} from "@/api/products";
import type { ProductInput } from "@/types";

function useInvalidateProducts() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["products"] });
}

export function useProducts(includeArchived = false) {
  return useQuery({
    queryKey: ["products", { includeArchived }],
    queryFn: () => fetchProducts(includeArchived),
  });
}

export function usePriceHistory(productId: number | null) {
  return useQuery({
    queryKey: ["products", "prices", productId],
    queryFn: () => fetchPriceHistory(productId as number),
    enabled: productId !== null,
  });
}

// Единицы засеваются при установке и не меняются — держим их в кэше долго,
// чтобы редактор позиций не ходил за ними при каждом открытии.
export function useUnits() {
  return useQuery({ queryKey: ["units"], queryFn: fetchUnits, staleTime: 60 * 60 * 1000 });
}

export function useCreateProduct() {
  const invalidate = useInvalidateProducts();
  return useMutation({ mutationFn: (input: ProductInput) => createProduct(input), onSuccess: invalidate });
}

export function useUpdateProduct() {
  const invalidate = useInvalidateProducts();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: Partial<ProductInput> }) => updateProduct(id, input),
    onSuccess: invalidate,
  });
}

export function useDeleteProduct() {
  const invalidate = useInvalidateProducts();
  return useMutation({ mutationFn: (id: number) => deleteProduct(id), onSuccess: invalidate });
}
