import { useQuery } from "@tanstack/react-query";
import { fetchNetWorthSummary } from "@/api/netWorth";
import type { NetWorthRange } from "@/types";

export function useNetWorthSummary(
  range: NetWorthRange,
  startDate?: string,
  endDate?: string,
  currency?: string
) {
  return useQuery({
    // Даты входят в ключ: без них запрос за 2023 год отдавал бы то же, что
    // за 2024, — из кэша, потому что «range» у них одинаковый. Валюта —
    // по той же причине: ответ в долларах и ответ в рублях это разные
    // ответы, а не разное оформление одного.
    queryKey: ["net-worth-summary", range, startDate ?? null, endDate ?? null, currency ?? null],
    queryFn: () => fetchNetWorthSummary(range, startDate, endDate, currency),
  });
}
