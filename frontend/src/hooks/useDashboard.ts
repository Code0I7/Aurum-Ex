import { useQuery } from "@tanstack/react-query";
import { fetchDashboardSummary } from "@/api/dashboard";
import type { DashboardRange } from "@/types";

export function useDashboardSummary(year: number, month: number, range: DashboardRange = "month") {
  return useQuery({
    queryKey: ["dashboard-summary", year, month, range],
    queryFn: () => fetchDashboardSummary(year, month, range),
  });
}
