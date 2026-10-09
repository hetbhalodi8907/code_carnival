/**
 * Centralized HTTP client: base URL, JSON, bearer token, error normalization and
 * session-expiry handling all live here, so components never touch tokens.
 */

import { API_BASE_URL } from "@/config/env";
import { clearSession, getAccessToken } from "@/services/session";
import type { ApiErrorBody } from "@/types/api";

export class ApiError extends Error {
  /** HTTP status, or 0 when the server could not be reached. */
  readonly status: number;
  readonly code: string | null;
  /** The backend's safe, user-facing message, when it sent one. */
  readonly serverMessage: string | null;

  constructor(status: number, code: string | null, serverMessage: string | null) {
    super(status === 0 ? "Network request failed" : `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.serverMessage = serverMessage;
  }

  /** FastAPI's default 404 for a route that does not exist (not a domain-level 404). */
  get isMissingRoute(): boolean {
    return this.status === 404 && this.serverMessage === "Not Found";
  }
}

type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

/** Registered by the auth provider; called when an authenticated request gets a 401. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler): () => void {
  unauthorizedHandler = handler;
  return () => {
    if (unauthorizedHandler === handler) unauthorizedHandler = null;
  };
}

interface RequestOptions {
  body?: unknown;
  /** Attach the bearer token (default true). Login is the only unauthenticated call. */
  auth?: boolean;
  signal?: AbortSignal;
}

function sessionExpired(): ApiError {
  clearSession();
  unauthorizedHandler?.();
  return new ApiError(401, "HTTP_ERROR", null);
}

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function errorFields(payload: unknown): { code: string | null; message: string | null } {
  const error = (payload as Partial<ApiErrorBody> | null)?.error;
  return {
    code: typeof error?.code === "string" ? error.code : null,
    message: typeof error?.message === "string" ? error.message : null,
  };
}

export async function apiRequest<T>(
  method: "GET" | "POST",
  path: string,
  { body, auth = true, signal }: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getAccessToken();
    if (!token) throw sessionExpired();
    headers.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError(0, "NETWORK_ERROR", null);
  }

  const payload = await readBody(response);
  if (!response.ok) {
    if (response.status === 401 && auth) throw sessionExpired();
    const { code, message } = errorFields(payload);
    // The backend always sends its error envelope; a bare 5xx comes from the dev proxy or
    // a gateway that could not reach it.
    if (response.status >= 500 && code === null) throw new ApiError(0, "BACKEND_UNREACHABLE", null);
    throw new ApiError(response.status, code, message);
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, "body">) => apiRequest<T>("GET", path, options),
  post: <T>(path: string, body: unknown, options?: Omit<RequestOptions, "body">) =>
    apiRequest<T>("POST", path, { ...options, body }),
};

export interface FriendlyError {
  title: string;
  message: string;
}

/** Map any failure to calm, non-technical copy. Raw server payloads are never shown. */
export function toFriendlyError(error: unknown): FriendlyError {
  const status = error instanceof ApiError ? error.status : -1;
  switch (status) {
    case 0:
      return { title: "Can't reach Nexora", message: "Check your connection and that the Nexora server is running." };
    case 401:
      return { title: "Session expired", message: "Please sign in again to continue." };
    case 403:
      return { title: "Access restricted", message: "Your account isn't permitted to perform this action." };
    case 404:
      return { title: "Not available yet", message: "This capability isn't available on the server yet." };
    case 422:
      return { title: "Invalid request", message: "Please check your question and try again." };
    case 502:
    case 503:
      return {
        title: "Service temporarily unavailable",
        message: "The AI service can't answer right now. Please try again shortly.",
      };
    default:
      return { title: "Something went wrong", message: "An unexpected error occurred. Please try again." };
  }
}
