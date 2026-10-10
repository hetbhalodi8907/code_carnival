import { useCallback, useEffect, useRef, useState } from "react";

import { toFriendlyError, type FriendlyError } from "@/services/api";
import { fetchDashboardOverview } from "@/services/dashboard";
import type { DashboardOverview } from "@/types/dashboard";

export interface DashboardState {
  data: DashboardOverview | null;
  error: FriendlyError | null;
  loading: boolean;
  refresh: () => void;
}

/** Loads the signed-in account's dashboard; a refresh keeps the previous data on screen while it runs. */
export function useDashboard(): DashboardState {
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [error, setError] = useState<FriendlyError | null>(null);
  const [loading, setLoading] = useState(true);
  const inFlight = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    setLoading(true);
    fetchDashboardOverview(controller.signal)
      .then((overview) => {
        setData(overview);
        setError(null);
      })
      .catch((failure: unknown) => {
        if (controller.signal.aborted) return;
        setError(toFriendlyError(failure));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, []);

  useEffect(() => {
    load();
    return () => inFlight.current?.abort();
  }, [load]);

  return { data, error, loading, refresh: load };
}
