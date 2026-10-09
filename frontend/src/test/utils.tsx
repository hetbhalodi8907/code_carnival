import { render } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { vi } from "vitest";

import { AppProviders } from "@/app/providers";
import { AppRoutes } from "@/app/router";
import { saveSession } from "@/services/session";
import type { CurrentUser } from "@/types/api";

export const FINANCE_MANAGER: CurrentUser = {
  id: "7b0d6a3e-0000-4000-8000-000000000001",
  email: "vikram.nair@nexora.example",
  full_name: "Vikram Nair",
  roles: ["FINANCE_MANAGER"],
  permissions: ["documents:read", "employee:self_read", "finance:read", "finance:write"],
};

export interface MockReply {
  status?: number;
  body?: unknown;
}
type Handler = MockReply | ((init: RequestInit) => MockReply | Promise<MockReply>);

export const NOT_FOUND: MockReply = {
  status: 404,
  body: { error: { code: "HTTP_ERROR", message: "Not Found", request_id: "test" } },
};

/** Route fetch calls by "METHOD /path"; unknown routes get FastAPI's 404 envelope. */
export function mockFetch(routes: Record<string, Handler>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const key = `${init.method ?? "GET"} ${new URL(url, "http://localhost").pathname}`;
    const route = routes[key];
    const reply = route === undefined ? NOT_FOUND : typeof route === "function" ? await route(init) : route;
    return new Response(reply.body === undefined ? null : JSON.stringify(reply.body), {
      status: reply.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function calls(fetchMock: ReturnType<typeof mockFetch>, method: string, path: string) {
  return fetchMock.mock.calls.filter(
    ([input, init]) => (init?.method ?? "GET") === method && String(input).endsWith(path),
  );
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

export function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppProviders>
        <AppRoutes />
        <LocationProbe />
      </AppProviders>
    </MemoryRouter>,
  );
}

/** Start a test already signed in (the server still confirms the user via /auth/me). */
export function signIn() {
  saveSession("test-access-token", 1800);
}
