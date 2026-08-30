import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createCryptoHolding,
  deleteCryptoHolding,
  fetchCryptoHoldings,
  refreshCryptoPrices,
  searchCryptoCoins,
  updateCryptoHoldingQuantity,
} from "@/api/crypto";
import type { CryptoHoldingInput } from "@/types";

function useInvalidateCrypto() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["crypto-holdings"] });
    // A crypto holding is a normal Asset under the hood — Net Worth's own
    // numbers change the moment one is added/edited/repriced/removed.
    queryClient.invalidateQueries({ queryKey: ["net-worth-summary"] });
  };
}

export function useCryptoHoldings() {
  return useQuery({ queryKey: ["crypto-holdings"], queryFn: fetchCryptoHoldings });
}

export function useRefreshCryptoPrices() {
  const invalidate = useInvalidateCrypto();
  return useMutation({ mutationFn: refreshCryptoPrices, onSuccess: invalidate });
}

export function useCreateCryptoHolding() {
  const invalidate = useInvalidateCrypto();
  return useMutation({
    mutationFn: (input: CryptoHoldingInput) => createCryptoHolding(input),
    onSuccess: invalidate,
  });
}

export function useUpdateCryptoHoldingQuantity() {
  const invalidate = useInvalidateCrypto();
  return useMutation({
    mutationFn: ({ assetId, quantity }: { assetId: number; quantity: string }) =>
      updateCryptoHoldingQuantity(assetId, quantity),
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

// Not a useQuery — this drives a search-as-you-type picker inside the "add
// holding" modal, called imperatively (debounced) rather than kept in sync
// with a query key.
export { searchCryptoCoins };
