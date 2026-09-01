import { api } from "@/api/client";
import type { HealthStatus } from "@/types";

export function fetchHealth() {
  return api.get<HealthStatus>("/health");
}
