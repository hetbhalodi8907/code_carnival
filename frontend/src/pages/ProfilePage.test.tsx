import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { getAccessToken } from "@/services/session";
import { FINANCE_MANAGER, mockFetch, renderApp, signIn } from "@/test/utils";

describe("profile page", () => {
  it("shows exactly what /auth/me returned: identity, roles and permissions", async () => {
    signIn();
    mockFetch({ "GET /api/v1/auth/me": { body: FINANCE_MANAGER } });
    renderApp("/app/profile");

    expect(await screen.findByRole("heading", { level: 2, name: "Vikram Nair" })).toBeInTheDocument();
    const roles = screen.getByRole("list", { name: "Roles" });
    expect(roles).toHaveTextContent("Finance Manager");
    expect(roles).toHaveTextContent("Authenticated");

    const permissions = screen.getByRole("list", { name: "Permissions" });
    expect(within(permissions).getAllByRole("listitem")).toHaveLength(FINANCE_MANAGER.permissions.length);
    for (const permission of FINANCE_MANAGER.permissions) {
      expect(permissions).toHaveTextContent(permission.replace(":", " · "));
    }
  });

  it("states when the session expires, from the issued token, and never shows the token", async () => {
    signIn();
    mockFetch({ "GET /api/v1/auth/me": { body: FINANCE_MANAGER } });
    renderApp("/app/profile");

    await screen.findByRole("heading", { level: 2, name: "Vikram Nair" });
    expect(screen.getByText("Session expires")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("test-access-token");
  });

  it("invents no permissions for an account that has none", async () => {
    signIn();
    mockFetch({ "GET /api/v1/auth/me": { body: { ...FINANCE_MANAGER, roles: [], permissions: [] } } });
    renderApp("/app/profile");

    expect(await screen.findByText("No permissions are assigned to this account.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Permissions" })).not.toBeInTheDocument();
    expect(screen.getAllByText("No role assigned").length).toBeGreaterThan(0);
  });

  it("logs out from the profile page", async () => {
    signIn();
    mockFetch({ "GET /api/v1/auth/me": { body: FINANCE_MANAGER } });
    const user = userEvent.setup();
    renderApp("/app/profile");

    await screen.findByRole("heading", { level: 2, name: "Vikram Nair" });
    const logoutButtons = screen.getAllByRole("button", { name: "Log out" });
    await user.click(logoutButtons[logoutButtons.length - 1]);

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/login"));
    expect(getAccessToken()).toBeNull();
  });
});
