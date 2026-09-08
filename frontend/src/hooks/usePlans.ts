import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createPlan,
  deletePlan,
  fetchPlanOverview,
  fetchPlans,
  fetchWatchlist,
  fetchHourlyRates,
  fetchWorkPeriods,
  saveWorkPeriod,
  updatePlan,
} from "@/api/plans";
import type { PlanInput, WorkPeriodInput } from "@/types";

// Правка плана меняет и список, и таблицу года — сбрасываются обе.
function useInvalidatePlans() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["plans"] });
  };
}

export function usePlans() {
  return useQuery({ queryKey: ["plans", "list"], queryFn: fetchPlans });
}

export function usePlanOverview(year: number) {
  return useQuery({ queryKey: ["plans", "overview", year], queryFn: () => fetchPlanOverview(year) });
}

export function useWatchlist(year: number) {
  return useQuery({ queryKey: ["plans", "watchlist", year], queryFn: () => fetchWatchlist(year) });
}

export function useCreatePlan() {
  const invalidate = useInvalidatePlans();
  return useMutation({ mutationFn: (input: PlanInput) => createPlan(input), onSuccess: invalidate });
}

export function useUpdatePlan() {
  const invalidate = useInvalidatePlans();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: Partial<PlanInput> }) => updatePlan(id, input),
    onSuccess: invalidate,
  });
}

export function useDeletePlan() {
  const invalidate = useInvalidatePlans();
  return useMutation({ mutationFn: (id: number) => deletePlan(id), onSuccess: invalidate });
}

export function useWorkPeriods(year: number) {
  return useQuery({ queryKey: ["work-periods", year], queryFn: () => fetchWorkPeriods(year) });
}

export function useSaveWorkPeriod() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: WorkPeriodInput) => saveWorkPeriod(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["work-periods"] });
      // Отработанные дни меняют планы «в рабочий день» — таблицу года надо
      // пересчитать, иначе февраль останется по календарным дням.
      queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
}

// Ставка меняется только при вводе отработанных часов — держим её в кэше
// долго, чтобы список операций не запрашивал её при каждой прокрутке.
export function useHourlyRates() {
  return useQuery({
    queryKey: ["work-periods", "hourly-rates"],
    queryFn: fetchHourlyRates,
    staleTime: 10 * 60 * 1000,
  });
}
