import { api } from "@/services/api";
import type { CurrentUser, LoginRequest, TokenResponse } from "@/types/api";

export function requestLogin(credentials: LoginRequest): Promise<TokenResponse> {
  return api.post<TokenResponse>("/api/v1/auth/login", credentials, { auth: false });
}

/** The backend is the source of truth for identity, roles and permissions. */
export function fetchCurrentUser(signal?: AbortSignal): Promise<CurrentUser> {
  return api.get<CurrentUser>("/api/v1/auth/me", { signal });
}
