import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { Bank, Counterparty, Participant, Store, Unit, UnitInput } from "@/types";

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
/** Имя из справочника подставлено в строки операций, в расчёты с людьми и
 *  в справочник товаров — после правки их все надо перечитать, иначе на
 *  экране останется старое имя рядом с новым. */
function invalidatePeople(queryClient: ReturnType<typeof useQueryClient>) {
  for (const key of ["participants", "stores", "counterparties", "transactions", "settlements", "products"]) {
    queryClient.invalidateQueries({ queryKey: [key] });
  }
}


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

/** Правка записи справочника. Переименование здесь — то же самое, что
 *  пакетное переименование во всех операциях сразу: они ссылаются на
 *  запись по номеру, а не по имени, поэтому исправление опечатки в одном
 *  месте исправляет её везде. */
export function useUpdateParticipant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: Partial<Participant> }) =>
      api.patch<Participant>(`/participants/${id}`, input),
    onSuccess: () => invalidatePeople(queryClient),
  });
}

export function useUpdateStore() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: Partial<Store> }) =>
      api.patch<Store>(`/stores/${id}`, input),
    onSuccess: () => invalidatePeople(queryClient),
  });
}

export function useUpdateCounterparty() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: Partial<Counterparty> }) =>
      api.patch<Counterparty>(`/counterparties/${id}`, input),
    onSuccess: () => invalidatePeople(queryClient),
  });
}

/** Удаление записи справочника. Ссылки на неё обнуляются базой: операции
 *  остаются, у них пустеет соответствующее поле. */
function useDeleteDirectory(path: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.delete<void>(`/${path}/${id}`),
    onSuccess: () => invalidatePeople(queryClient),
  });
}

export const useDeleteParticipant = () => useDeleteDirectory("participants");
export const useDeleteStore = () => useDeleteDirectory("stores");
export const useDeleteCounterparty = () => useDeleteDirectory("counterparties");


function invalidateUnits(queryClient: ReturnType<typeof useQueryClient>) {
  // Единица подставлена в позиции чеков и участвует в приведении к базовой
  // мере, поэтому вместе с ней перечитываются товары и их история цен.
  for (const key of ["units", "products", "transactions"]) {
    queryClient.invalidateQueries({ queryKey: [key] });
  }
}

export function useCreateUnit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UnitInput) => api.post<Unit>("/units", payload),
    onSuccess: () => invalidateUnits(queryClient),
  });
}

export function useUpdateUnit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: Partial<UnitInput> }) =>
      api.patch<Unit>(`/units/${id}`, input),
    onSuccess: () => invalidateUnits(queryClient),
  });
}

export function useDeleteUnit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.delete<void>(`/units/${id}`),
    onSuccess: () => invalidateUnits(queryClient),
  });
}
