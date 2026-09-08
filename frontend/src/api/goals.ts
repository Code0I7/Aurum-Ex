import { api } from "@/api/client";
import type { AccountReservation, Goal, GoalContributionInput, GoalInput } from "@/types";

export function fetchGoals() {
  return api.get<Goal[]>("/goals");
}

/** Чем занята часть остатка каждого счёта — по целям. Для полосы на
 *  обзоре: один отрезок на цель, с подписью, на что отложено. */
export function fetchReservations() {
  return api.get<AccountReservation[]>("/goals/reservations");
}

export function createGoal(input: GoalInput) {
  return api.post<Goal>("/goals", input);
}

export function updateGoal(id: number, input: Partial<GoalInput>) {
  return api.patch<Goal>(`/goals/${id}`, input);
}

export function deleteGoal(id: number) {
  return api.delete<void>(`/goals/${id}`);
}

export function addGoalContribution(id: number, input: GoalContributionInput) {
  return api.post<Goal>(`/goals/${id}/contributions`, input);
}
