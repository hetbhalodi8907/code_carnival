import { createContext } from "react";

import type { CurrentUser } from "@/types/api";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

export interface AuthContextValue {
  status: AuthStatus;
  /** Exactly what GET /api/v1/auth/me returned; never edited client-side. */
  user: CurrentUser | null;
  /** One-off message for the login page, e.g. after a session expires. */
  notice: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export const SESSION_EXPIRED_NOTICE = "Your session has expired. Please sign in again.";
