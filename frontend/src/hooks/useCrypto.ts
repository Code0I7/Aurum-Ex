import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addCryptoTransaction,
  createCryptoHolding,
  deleteCryptoHolding,
  deleteCryptoTransaction,
  fetchCryptoHistory,
  fetchCryptoHoldings,
  fetchCryptoTransactions,
  refreshCryptoPrices,
  updateCryptoTransaction,
} from "@/api/crypto";
import type { CryptoHoldingCreateInput, CryptoRange, CryptoTransactionInput } from "@/types";

function useInvalidateCrypto() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["crypto-holdings"] });
    queryClient.invalidateQueries({ queryKey: ["crypto-transactions"] });
    queryClient.invalidateQueries({ queryKey: ["crypto-history"] });
    // A crypto holding is a normal Asset under the hood — Net Worth's own
    // numbers change the moment one is added/traded/repriced/removed.
    queryClient.invalidateQueries({ queryKey: ["net-worth-summary"] });
  };
}

export function useCryptoHoldings() {
  return useQuery({ queryKey: ["crypto-holdings"], queryFn: fetchCryptoHoldings });
}

export function useCryptoHistory(range: CryptoRange) {
  return useQuery({ queryKey: ["crypto-history", range], queryFn: () => fetchCryptoHistory(range) });
}

export function useCryptoTransactions(assetId: number | null) {
  return useQuery({
    queryKey: ["crypto-transactions", assetId],
    queryFn: () => fetchCryptoTransactions(assetId!),
    enabled: assetId !== null,
  });
}

export function useRefreshCryptoPrices() {
  const invalidate = useInvalidateCrypto();
  return useMutation({ mutationFn: refreshCryptoPrices, onSuccess: invalidate });
}

export function useCreateCryptoHolding() {
  const invalidate = useInvalidateCrypto();
  return useMutation({
    mutationFn: (input: CryptoHoldingCreateInput) => createCryptoHolding(input),
    onSuccess: invalidate,
  });
}

export function useAddCryptoTransaction() {
  const invalidate = useInvalidateCrypto();
  return useMutation({
    mutationFn: ({ assetId, input }: { assetId: number; input: CryptoTransactionInput }) =>
      addCryptoTransaction(assetId, input),
    onSuccess: invalidate,
  });
}

export function useUpdateCryptoTransaction() {
  const invalidate = useInvalidateCrypto();
  return useMutation({
    mutationFn: ({ transactionId, input }: { transactionId: number; input: CryptoTransactionInput }) =>
      updateCryptoTransaction(transactionId, input),
    onSuccess: invalidate,
  });
}

export function useDeleteCryptoTransaction() {
  const invalidate = useInvalidateCrypto();
  return useMutation({
    mutationFn: (transactionId: number) => deleteCryptoTransaction(transactionId),
    onSuccess: invalidate,
  });
}

export function useDeleteCryptoHolding() {
  const invalidate = useInvalidateCrypto();
  return useMutation({
    mutationFn: (assetId: number) => deleteCryptoHolding(assetId),
    onSuccess: invalidate,
  });
}
