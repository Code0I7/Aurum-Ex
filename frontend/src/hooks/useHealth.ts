import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "@/api/health";

// The running version only changes on a deploy (a full page reload), so
// there's no need to ever refetch within a session.
export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: fetchHealth, staleTime: Infinity });
}
