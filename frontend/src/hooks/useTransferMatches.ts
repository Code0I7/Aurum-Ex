import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dismissTransferMatch, fetchTransferMatches, mergeTransferMatch } from "@/api/transferMatches";
import { invalidateMoneyQueries } from "@/lib/queryInvalidation";

export function useTransferMatches() {
  return useQuery({ queryKey: ["transfer-matches"], queryFn: fetchTransferMatches });
}

/** Склейка меняет вид операции и удаляет вторую запись — это правка денег,
 * и перезапрашивается всё, что от них зависит (сам список пар тоже). */
export function useMergeTransferMatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ keepId, dropId }: { keepId: number; dropId: number }) => mergeTransferMatch(keepId, dropId),
    onSuccess: () => invalidateMoneyQueries(queryClient),
  });
}

/** Отказ денег не касается: меняется только список пар. */
export function useDismissTransferMatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ keepId, dropId }: { keepId: number; dropId: number }) => dismissTransferMatch(keepId, dropId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["transfer-matches"] }),
  });
}
