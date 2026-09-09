import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteCreditTerms,
  fetchCredits,
  fetchCreditSummary,
  fetchSettlements,
  fetchSettlementSummary,
  fetchTransitSummary,
  saveCreditTerms,
} from "@/api/debts";
import type { CreditTermsInput } from "@/types";

// Правка условий меняет и список кредитов, и сводку, и карточку счёта
// (доступный остаток считается из лимита) — поэтому сбрасываются все три.
function useInvalidateCredits() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["credits"] });
    queryClient.invalidateQueries({ queryKey: ["accounts"] });
  };
}

export function useSettlements() {
  return useQuery({ queryKey: ["settlements"], queryFn: fetchSettlements });
}

export function useSettlementSummary() {
  return useQuery({ queryKey: ["settlements", "summary"], queryFn: fetchSettlementSummary });
}

export function useTransitSummary() {
  return useQuery({ queryKey: ["settlements", "transit"], queryFn: fetchTransitSummary });
}

export function useCredits() {
  return useQuery({ queryKey: ["credits"], queryFn: fetchCredits });
}

export function useCreditSummary() {
  return useQuery({ queryKey: ["credits", "summary"], queryFn: fetchCreditSummary });
}

export function useSaveCreditTerms() {
  const invalidate = useInvalidateCredits();
  return useMutation({
    mutationFn: ({ accountId, input }: { accountId: number; input: CreditTermsInput }) =>
      saveCreditTerms(accountId, input),
    onSuccess: invalidate,
  });
}

export function useDeleteCreditTerms() {
  const invalidate = useInvalidateCredits();
  return useMutation({
    mutationFn: (accountId: number) => deleteCreditTerms(accountId),
    onSuccess: invalidate,
  });
}
