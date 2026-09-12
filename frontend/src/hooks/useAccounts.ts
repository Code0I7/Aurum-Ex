import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createAccount, deleteAccount, fetchAccounts, updateAccount } from "@/api/accounts";
import { invalidateMoneyQueries } from "@/lib/queryInvalidation";
import type { AccountInput } from "@/types";

export function useAccounts(includeArchived = false) {
  return useQuery({ queryKey: ["accounts", includeArchived], queryFn: () => fetchAccounts(includeArchived) });
}

export function useCreateAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: AccountInput) => createAccount(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["accounts"] }),
  });
}

export function useUpdateAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: Partial<AccountInput> & { is_archived?: boolean } }) =>
      updateAccount(id, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["accounts"] }),
  });
}

export function useDeleteAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteAccount(id),
    // A cascade-deleted account takes its transaction history with it —
    // refresh everything derived from transactions.
    //
    // Здесь стоял третий по счёту список «что от этого устарело», и он, как
    // и остальные, не знал про расчёты с людьми: удалив счёт, человек видел
    // прежние долги. Теперь список один на всех.
    onSuccess: () => invalidateMoneyQueries(queryClient),
  });
}
