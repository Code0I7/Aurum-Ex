import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addAssetValuation,
  createAsset,
  deleteAsset,
  deleteAssetValuation,
  fetchAssets,
  fetchAssetValuations,
  updateAsset,
} from "@/api/assets";
import type { AssetInput, AssetUpdateInput, AssetValuationInput } from "@/types";

function useInvalidateNetWorth() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["assets"] });
    queryClient.invalidateQueries({ queryKey: ["net-worth-summary"] });
  };
}

export function useAssets() {
  return useQuery({ queryKey: ["assets"], queryFn: fetchAssets });
}

export function useCreateAsset() {
  const invalidate = useInvalidateNetWorth();
  return useMutation({
    mutationFn: (input: AssetInput) => createAsset(input),
    onSuccess: invalidate,
  });
}

export function useUpdateAsset() {
  const invalidate = useInvalidateNetWorth();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: AssetUpdateInput }) => updateAsset(id, input),
    onSuccess: invalidate,
  });
}

export function useAddAssetValuation() {
  const invalidate = useInvalidateNetWorth();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: AssetValuationInput }) => addAssetValuation(id, input),
    onSuccess: invalidate,
  });
}

/** История переоценок одного актива. Запрашивается только при открытой
 *  правке: на списке активов она не нужна, а запрос на каждый актив стоил бы
 *  дороже пользы. */
export function useAssetValuations(id: number | null) {
  return useQuery({
    queryKey: ["assets", id, "valuations"],
    queryFn: () => fetchAssetValuations(id as number),
    enabled: id !== null,
  });
}

export function useDeleteAssetValuation() {
  const invalidate = useInvalidateNetWorth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, valuationId }: { id: number; valuationId: number }) =>
      deleteAssetValuation(id, valuationId),
    onSuccess: (_data, variables) => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["assets", variables.id, "valuations"] });
    },
  });
}

export function useDeleteAsset() {
  const invalidate = useInvalidateNetWorth();
  return useMutation({
    mutationFn: (id: number) => deleteAsset(id),
    onSuccess: invalidate,
  });
}
