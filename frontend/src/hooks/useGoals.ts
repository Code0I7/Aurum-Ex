import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addGoalContribution,
  createGoal,
  deleteGoal,
  fetchGoals,
  fetchReservations,
  updateGoal,
} from "@/api/goals";
import { invalidateMoneyQueries } from "@/lib/queryInvalidation";
import type { GoalContributionInput, GoalInput } from "@/types";

/**
 * Цель — тоже про деньги: взнос увеличивает отложенное, а оно уменьшает
 * доступное на счёте. Обновлять один список целей значило бы оставить на
 * карточке счёта прежнее «доступно» — число, ради которого на неё и
 * смотрят.
 */
function useInvalidateGoals() {
  const queryClient = useQueryClient();
  return () => invalidateMoneyQueries(queryClient);
}

export function useGoals() {
  return useQuery({ queryKey: ["goals"], queryFn: fetchGoals });
}

export function useCreateGoal() {
  const invalidate = useInvalidateGoals();
  return useMutation({
    mutationFn: (input: GoalInput) => createGoal(input),
    onSuccess: invalidate,
  });
}

/** Резервы по счетам — для полосы на обзоре. Отдельный запрос, а не
 *  часть списка целей: обзору не нужны сами цели, а списку целей не нужна
 *  разбивка по счетам в обратную сторону. */
export function useReservations() {
  return useQuery({ queryKey: ["goals", "reservations"], queryFn: fetchReservations });
}

export function useUpdateGoal() {
  const invalidate = useInvalidateGoals();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: Partial<GoalInput> }) => updateGoal(id, input),
    onSuccess: invalidate,
  });
}

export function useDeleteGoal() {
  const invalidate = useInvalidateGoals();
  return useMutation({
    mutationFn: (id: number) => deleteGoal(id),
    onSuccess: invalidate,
  });
}

export function useAddGoalContribution() {
  const invalidate = useInvalidateGoals();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: GoalContributionInput }) => addGoalContribution(id, input),
    onSuccess: invalidate,
  });
}
