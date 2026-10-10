import { api } from "@/services/api";
import type { DashboardOverview } from "@/types/dashboard";

/** The server decides which sections this account receives; the request carries no role or scope. */
export function fetchDashboardOverview(signal?: AbortSignal): Promise<DashboardOverview> {
  return api.get<DashboardOverview>("/api/v1/dashboard/overview", { signal });
}
