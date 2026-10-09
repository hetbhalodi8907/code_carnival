import { Navigate, Outlet, useLocation } from "react-router";

import { PageStatus } from "@/components/feedback/PageStatus";
import { useAuth } from "@/context/useAuth";

/**
 * UX-only route guard: it keeps signed-out visitors on the login page.
 * Real protection is the backend, which validates the token on every API call.
 */
export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <PageStatus>Restoring your secure session…</PageStatus>;
  if (status !== "authenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
