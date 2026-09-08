import { api } from "@/api/client";
import type { NetWorthRange, NetWorthSummary } from "@/types";

export function fetchNetWorthSummary(range: NetWorthRange, startDate?: string, endDate?: string) {
  const query = new URLSearchParams({ range });
  if (startDate) query.set("start_date", startDate);
  if (endDate) query.set("end_date", endDate);
  return api.get<NetWorthSummary>(`/net-worth/summary?${query.toString()}`);
}
