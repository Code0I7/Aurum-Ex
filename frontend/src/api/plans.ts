import { api } from "@/api/client";
import type { Plan, PlanInput, PlanOverview, WorkPeriod, WorkPeriodInput } from "@/types";

export function fetchPlans() {
  return api.get<Plan[]>("/plans");
}

export function fetchPlanOverview(year: number) {
  return api.get<PlanOverview>(`/plans/overview?year=${year}`);
}

export function createPlan(input: PlanInput) {
  return api.post<Plan>("/plans", input);
}

export function updatePlan(id: number, input: Partial<PlanInput>) {
  return api.patch<Plan>(`/plans/${id}`, input);
}

export function deletePlan(id: number) {
  return api.delete<void>(`/plans/${id}`);
}

export function fetchWorkPeriods(year: number) {
  return api.get<WorkPeriod[]>(`/work-periods?year=${year}`);
}

// PUT: у месяца либо есть отработанное время, либо нет — второй записи за
// тот же месяц не бывает.
export function saveWorkPeriod(input: WorkPeriodInput) {
  return api.put<WorkPeriod>("/work-periods", input);
}
