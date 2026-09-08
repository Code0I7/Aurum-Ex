import { api } from "@/api/client";
import type { HourlyRates } from "@/lib/hours";
import type { Plan, PlanInput, PlanOverview, Watchlist, WorkPeriod, WorkPeriodInput } from "@/types";

export function fetchPlans() {
  return api.get<Plan[]>("/plans");
}

export function fetchPlanOverview(year: number) {
  return api.get<PlanOverview>(`/plans/overview?year=${year}`);
}

// Список наблюдения. Отдельный запрос, а не часть таблицы года: его
// строки живут по другим правилам — по всей ветке и без плана.
export function fetchWatchlist(year: number) {
  return api.get<Watchlist>(`/plans/watchlist?year=${year}`);
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

// Ставка за час по месяцам. Помесячно, а не одной цифрой: за четыре года
// заработок меняется втрое, и покупка 2022 года по сегодняшней ставке
// выглядела бы втрое дешевле, чем была.
export function fetchHourlyRates() {
  return api.get<HourlyRates>("/work-periods/hourly-rates");
}
