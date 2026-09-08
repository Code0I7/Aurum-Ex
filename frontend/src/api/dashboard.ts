import { api } from "@/api/client";
import type { DashboardRange, DashboardSummary } from "@/types";

export function fetchDashboardSummary(year: number, month: number, range: DashboardRange = "month") {
  return api.get<DashboardSummary>(
    `/dashboard/summary?year=${year}&month=${month}&range=${range}`,
  );
}
