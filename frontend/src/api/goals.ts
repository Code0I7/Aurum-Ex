import { api } from "@/api/client";
import type {
  AccountReservation,
  Goal,
  GoalContribution,
  GoalContributionInput,
  GoalInput,
} from "@/types";

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

/** История накопления: чем и когда набралась нынешняя сумма. */
export function fetchGoalContributions(id: number) {
  return api.get<GoalContribution[]>(`/goals/${id}/contributions`);
}

/** Правка и удаление отвечают самой целью: убрав или поправив взнос,
 *  интерфейс обязан сразу показать новое «накоплено». */
export function updateGoalContribution(
  goalId: number,
  contributionId: number,
  input: Partial<GoalContributionInput>
) {
  return api.patch<Goal>(`/goals/${goalId}/contributions/${contributionId}`, input);
}

export function deleteGoalContribution(goalId: number, contributionId: number) {
  return api.delete<Goal>(`/goals/${goalId}/contributions/${contributionId}`);
}
