import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { getAccessToken } from "@/services/session";
import { FINANCE_MANAGER, calls, mockFetch, renderApp, signIn } from "@/test/utils";

const LOGIN_OK = { body: { access_token: "issued-token", token_type: "bearer", expires_in: 1800 } };

describe("authentication flow", () => {
  it("signs in, loads the user from /auth/me and opens the assistant", async () => {
    const fetchMock = mockFetch({ "POST /api/v1/auth/login": LOGIN_OK, "GET /api/v1/auth/me": { body: FINANCE_MANAGER } });
    const user = userEvent.setup();
    renderApp("/login");

    await user.type(screen.getByLabelText("Work email"), "vikram.nair@nexora.example");
    await user.type(screen.getByLabelText("Password"), "correct-password");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/app/chat"));
    expect(screen.getByTestId("current-user-name")).toHaveTextContent("Vikram Nair");
    expect(screen.getByTestId("current-user-role")).toHaveTextContent("Finance Manager");
    expect(JSON.parse(String(calls(fetchMock, "POST", "/api/v1/auth/login")[0][1]?.body))).toEqual({
      email: "vikram.nair@nexora.example",
      password: "correct-password",
    });
    const meHeaders = calls(fetchMock, "GET", "/api/v1/auth/me")[0][1]?.headers as Record<string, string>;
    expect(meHeaders.Authorization).toBe("Bearer issued-token");
    expect(document.body.textContent).not.toContain("issued-token");
  });

  it("shows a safe error for invalid credentials and clears the password", async () => {
    mockFetch({
      "POST /api/v1/auth/login": {
        status: 401,
        body: { error: { code: "HTTP_ERROR", message: "Invalid email or password.", request_id: "r" } },
      },
    });
    const user = userEvent.setup();
    renderApp("/login");

    await user.type(screen.getByLabelText("Work email"), "someone@nexora.example");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(screen.getByTestId("location")).toHaveTextContent("/login");
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(getAccessToken()).toBeNull();
  });

  it("says the server is unreachable when the dev proxy cannot reach the backend", async () => {
    mockFetch({ "POST /api/v1/auth/login": { status: 500 } });
    const user = userEvent.setup();
    renderApp("/login");

    await user.type(screen.getByLabelText("Work email"), "kabir.sethi@nexora.example");
    await user.type(screen.getByLabelText("Password"), "DemoEmployee@2026");
    await user.click(screen.getByRole("button", { name: "Log in as Employee" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach the Nexora server.");
    expect(getAccessToken()).toBeNull();
  });

  it("redirects unauthenticated visitors from protected routes to /login", async () => {
    mockFetch({});
    renderApp("/app/chat");

    expect(await screen.findByRole("heading", { name: "Log in to NEXORA" })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/login");
  });

  it("restores a saved session only after the server confirms the user", async () => {
    signIn();
    mockFetch({ "GET /api/v1/auth/me": { body: FINANCE_MANAGER } });
    renderApp("/app/profile");

    expect(await screen.findByRole("heading", { name: "Profile" })).toBeInTheDocument();
    expect(screen.getByText("finance · write")).toBeInTheDocument();
  });

  it("signs out, clears the session and returns to /login", async () => {
    signIn();
    mockFetch({ "GET /api/v1/auth/me": { body: FINANCE_MANAGER } });
    const user = userEvent.setup();
    renderApp("/app/chat");

    await user.click(await screen.findByRole("button", { name: "Log out" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/login"));
    expect(getAccessToken()).toBeNull();
    // The signed-in identity is gone (the name may still appear on a demo card).
    expect(screen.queryByTestId("current-user-name")).not.toBeInTheDocument();
    expect(screen.queryByTestId("session-card")).not.toBeInTheDocument();
  });
});
