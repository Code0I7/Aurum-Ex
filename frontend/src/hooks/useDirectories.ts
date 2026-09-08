import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { Bank, Counterparty, Participant, Store } from "@/types";

/**
 * Справочники, на которые ссылается транзакция.
 *
 * Один файл на четыре сущности: они устроены одинаково, и разносить четыре
 * копии одного хука по четырём файлам значило бы четырежды чинить одну и ту
 * же ошибку. То же соображение, что и на бэкенде (routes/directories.py).
 *
 * Списки живут дольше обычного (5 минут вместо 30 секунд по умолчанию):
 * участники и магазины меняются раз в месяц, а запрашиваются в каждой форме
 * ввода, и перезапрашивать их на каждое открытие незачем.
 */
const DIRECTORY_STALE_TIME = 5 * 60_000;

export function useBanks() {
  return useQuery({
    queryKey: ["banks"],
    queryFn: () => api.get<Bank[]>("/banks"),
    staleTime: DIRECTORY_STALE_TIME,
  });
}

export function useParticipants(includeArchived = false) {
  return useQuery({
    queryKey: ["participants", includeArchived],
    queryFn: () => api.get<Participant[]>(`/participants?include_archived=${includeArchived}`),
    staleTime: DIRECTORY_STALE_TIME,
  });
}

export function useStores(includeArchived = false) {
  return useQuery({
    queryKey: ["stores", includeArchived],
    queryFn: () => api.get<Store[]>(`/stores?include_archived=${includeArchived}`),
    staleTime: DIRECTORY_STALE_TIME,
  });
}

export function useCounterparties(includeArchived = false) {
  return useQuery({
    queryKey: ["counterparties", includeArchived],
    queryFn: () => api.get<Counterparty[]>(`/counterparties?include_archived=${includeArchived}`),
    staleTime: DIRECTORY_STALE_TIME,
  });
}

/** Создание прямо из формы ввода: набрал новое имя — оно завелось. Ходить
 * за этим в настройки значило бы прерывать ввод транзакции ради заведения
 * магазина, и в итоге поле просто перестали бы заполнять. */
export function useCreateParticipant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; kind?: "person" | "pet" }) =>
      api.post<Participant>("/participants", payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["participants"] }),
  });
}

export function useCreateStore() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; location?: string | null }) => api.post<Store>("/stores", payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["stores"] }),
  });
}

export function useCreateCounterparty() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string }) => api.post<Counterparty>("/counterparties", payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["counterparties"] }),
  });
}
