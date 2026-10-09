import { describe, expect, it, vi } from "vitest";

import { ApiError, api, setUnauthorizedHandler, toFriendlyError } from "@/services/api";
import { getAccessToken } from "@/services/session";
import { mockFetch, signIn } from "@/test/utils";

describe("api client", () => {
  it("attaches the bearer token and JSON headers to authenticated requests", async () => {
    signIn();
    const fetchMock = mockFetch({ "POST /api/v1/search/vector": { body: { results: [] } } });

    await api.post("/api/v1/search/vector", { query: "budget" });

    const [, init] = fetchMock.mock.calls[0];
    const headers = init?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer test-access-token");
    expect(headers["Content-Type"]).toBe("application/json");
    expect(init?.body).toBe(JSON.stringify({ query: "budget" }));
  });

  it("never sends a token on unauthenticated calls such as login", async () => {
    signIn();
    const fetchMock = mockFetch({ "POST /api/v1/auth/login": { body: {} } });

    await api.post("/api/v1/auth/login", { email: "a@b.c", password: "x" }, { auth: false });

    expect((fetchMock.mock.calls[0][1]?.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("clears the session and notifies the app when the server answers 401", async () => {
    signIn();
    mockFetch({ "GET /api/v1/auth/me": { status: 401, body: { error: { code: "HTTP_ERROR", message: "x" } } } });
    const handler = vi.fn();
    const unsubscribe = setUnauthorizedHandler(handler);

    await expect(api.get("/api/v1/auth/me")).rejects.toMatchObject({ status: 401 });

    expect(handler).toHaveBeenCalledOnce();
    expect(getAccessToken()).toBeNull();
    unsubscribe();
  });

  it("reports unreachable servers as status 0", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(api.post("/api/v1/auth/login", {}, { auth: false })).rejects.toMatchObject({ status: 0 });
  });

  it("treats a bare 5xx from the dev proxy as unreachable, but keeps the backend's own 5xx", async () => {
    // The Vite proxy answers an empty 500 when the backend is down.
    mockFetch({ "POST /api/v1/auth/login": { status: 500 } });
    await expect(api.post("/api/v1/auth/login", {}, { auth: false })).rejects.toMatchObject({ status: 0 });

    signIn();
    mockFetch({
      "POST /api/v1/search/vector": {
        status: 503,
        body: { error: { code: "HTTP_ERROR", message: "Embedding provider unavailable.", request_id: "r" } },
      },
    });
    await expect(api.post("/api/v1/search/vector", {})).rejects.toMatchObject({ status: 503 });
  });

  it("maps failures to friendly copy without exposing server payloads", () => {
    const leaky = new ApiError(503, "HTTP_ERROR", "Internal detail: embedding provider at 10.0.0.5");
    expect(toFriendlyError(leaky).title).toBe("Service temporarily unavailable");
    expect(JSON.stringify(toFriendlyError(leaky))).not.toContain("10.0.0.5");
    expect(toFriendlyError(new ApiError(422, null, null)).title).toBe("Invalid request");
    expect(toFriendlyError(new ApiError(500, null, null)).title).toBe("Something went wrong");
    expect(toFriendlyError(new Error("boom")).title).toBe("Something went wrong");
    expect(new ApiError(404, "HTTP_ERROR", "Not Found").isMissingRoute).toBe(true);
    expect(new ApiError(404, "HTTP_ERROR", "The document does not exist.").isMissingRoute).toBe(false);
  });
});
