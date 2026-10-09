import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { AuthContext, SESSION_EXPIRED_NOTICE, type AuthContextValue, type AuthStatus } from "@/context/auth-context";
import { setUnauthorizedHandler } from "@/services/api";
import { fetchCurrentUser, requestLogin } from "@/services/auth";
import { clearSession, loadSession, saveSession } from "@/services/session";
import type { CurrentUser } from "@/types/api";

interface AuthState {
  status: AuthStatus;
  user: CurrentUser | null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => ({
    status: loadSession() ? "loading" : "anonymous",
    user: null,
  }));
  const [notice, setNotice] = useState<string | null>(null);
  const expiryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const endSession = useCallback((reason: "manual" | "expired") => {
    if (expiryTimer.current) clearTimeout(expiryTimer.current);
    expiryTimer.current = null;
    clearSession();
    setState({ status: "anonymous", user: null });
    setNotice(reason === "expired" ? SESSION_EXPIRED_NOTICE : null);
  }, []);

  const scheduleExpiry = useCallback(
    (expiresAt: number) => {
      if (expiryTimer.current) clearTimeout(expiryTimer.current);
      expiryTimer.current = setTimeout(() => endSession("expired"), Math.max(0, expiresAt - Date.now()));
    },
    [endSession],
  );

  // Any authenticated request that receives 401 ends the session.
  useEffect(() => setUnauthorizedHandler(() => endSession("expired")), [endSession]);

  // Restore a session from this tab after a reload: the server re-confirms the user.
  useEffect(() => {
    const session = loadSession();
    if (!session) return;
    const controller = new AbortController();
    fetchCurrentUser(controller.signal)
      .then((user) => {
        setState({ status: "authenticated", user });
        scheduleExpiry(session.expiresAt);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        clearSession();
        setState({ status: "anonymous", user: null });
      });
    return () => controller.abort();
  }, [scheduleExpiry]);

  useEffect(
    () => () => {
      if (expiryTimer.current) clearTimeout(expiryTimer.current);
    },
    [],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const token = await requestLogin({ email, password });
      const session = saveSession(token.access_token, token.expires_in);
      try {
        const user = await fetchCurrentUser();
        setState({ status: "authenticated", user });
        setNotice(null);
        scheduleExpiry(session.expiresAt);
      } catch (error) {
        clearSession();
        throw error;
      }
    },
    [scheduleExpiry],
  );

  const logout = useCallback(() => endSession("manual"), [endSession]);

  const value = useMemo<AuthContextValue>(
    () => ({ status: state.status, user: state.user, notice, login, logout }),
    [state, notice, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
