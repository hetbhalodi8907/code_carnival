import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { DEMO_ACCOUNTS } from "@/config/demoAccounts";
import { getAccessToken } from "@/services/session";
import type { CurrentUser } from "@/types/api";
import { calls, mockFetch, renderApp, signIn } from "@/test/utils";

const SUPER_ADMIN_USER: CurrentUser = {
  id: "7b0d6a3e-0000-4000-8000-000000000009",
  email: "ishaan.malhotra@nexora.example",
  full_name: "Ishaan Malhotra",
  roles: ["SUPER_ADMIN"],
  permissions: ["documents:read", "documents:write", "finance:read", "hr:read"],
};

const LOGIN_OK = { body: { access_token: "issued-token", token_type: "bearer", expires_in: 1800 } };

describe("hackathon demo accounts", () => {
  it("renders one card per role with real seeded emails and demo passwords", () => {
    mockFetch({});
    renderApp("/login");

    const expected: Record<string, string> = {
      SUPER_ADMIN: "CEO / Super Admin",
      HR_MANAGER: "HR Manager",
      FINANCE_MANAGER: "Finance Manager",
      ENGINEERING_MANAGER: "Engineering Manager",
      SECURITY_MANAGER: "Security Manager",
      EMPLOYEE: "Employee",
    };
    expect(DEMO_ACCOUNTS).toHaveLength(6);
    for (const account of DEMO_ACCOUNTS) {
      const card = screen.getByTestId(`demo-account-${account.role}`);
      expect(card).toHaveTextContent(expected[account.role]);
      expect(card).toHaveTextContent(account.email);
      expect(card).toHaveTextContent(account.password);
      expect(card).toHaveAttribute("aria-pressed", "false");
    }
    expect(screen.getByText(/Local demo credentials · not for production/)).toBeInTheDocument();
  });

  it("fills the form, marks the role as selected and does not log in by itself", async () => {
    const fetchMock = mockFetch({});
    const user = userEvent.setup();
    renderApp("/login");
    const finance = DEMO_ACCOUNTS.find((account) => account.role === "FINANCE_MANAGER")!;

    await user.click(screen.getByTestId("demo-account-FINANCE_MANAGER"));

    expect(screen.getByLabelText("Work email")).toHaveValue(finance.email);
    expect(screen.getByLabelText("Password")).toHaveValue(finance.password);
    expect(screen.getByTestId("demo-account-FINANCE_MANAGER")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("selected-demo-account")).toHaveTextContent("Finance ManagerVikram Nair · vikram.nair@nexora.example");
    const submit = screen.getByRole("button", { name: "Log in as Finance Manager" });
    expect(submit).toHaveFocus();
    expect(fetchMock).not.toHaveBeenCalled();

    // Editing a field clears the selection: it is derived from the form, not stored.
    await user.type(screen.getByLabelText("Password"), "x");
    expect(screen.queryByTestId("selected-demo-account")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log in" })).toBeInTheDocument();
  });

  it("logs in through the real API and shows the server's identity as authenticated", async () => {
    const fetchMock = mockFetch({
      "POST /api/v1/auth/login": LOGIN_OK,
      "GET /api/v1/auth/me": { body: SUPER_ADMIN_USER },
    });
    const user = userEvent.setup();
    renderApp("/login");
    const ceo = DEMO_ACCOUNTS.find((account) => account.role === "SUPER_ADMIN")!;

    await user.click(screen.getByTestId("demo-account-SUPER_ADMIN"));
    await user.click(screen.getByRole("button", { name: "Log in as CEO / Super Admin" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/app/chat"));
    expect(JSON.parse(String(calls(fetchMock, "POST", "/api/v1/auth/login")[0][1]?.body))).toEqual({
      email: ceo.email,
      password: ceo.password,
    });
    const session = screen.getByTestId("session-card");
    expect(within(session).getByTestId("auth-state")).toHaveTextContent("Authenticated");
    expect(session).toHaveTextContent("Ishaan Malhotra");
    expect(within(session).getByTestId("session-email")).toHaveTextContent(ceo.email);
    expect(session).toHaveTextContent("CEO / Super Admin");
    expect(session).toHaveTextContent("4 server-granted permissions");
    expect(screen.getByTestId("current-user-role")).toHaveTextContent("CEO / Super Admin");
  });

  it("displays only what /auth/me returns, not what the card claimed", async () => {
    // The server says this account is an Employee: the UI must show Employee.
    mockFetch({
      "POST /api/v1/auth/login": LOGIN_OK,
      "GET /api/v1/auth/me": {
        body: { ...SUPER_ADMIN_USER, roles: ["EMPLOYEE"], permissions: ["documents:read"] },
      },
    });
    const user = userEvent.setup();
    renderApp("/login");

    await user.click(screen.getByTestId("demo-account-SUPER_ADMIN"));
    await user.click(screen.getByRole("button", { name: "Log in as CEO / Super Admin" }));

    await waitFor(() => expect(screen.getByTestId("current-user-role")).toHaveTextContent("Employee"));
    expect(screen.getByTestId("session-card")).not.toHaveTextContent("CEO / Super Admin");
  });

  it("logs out completely from the visible Log out button", async () => {
    signIn();
    mockFetch({ "GET /api/v1/auth/me": { body: SUPER_ADMIN_USER } });
    const user = userEvent.setup();
    renderApp("/app/chat");

    await user.click(await screen.findByRole("button", { name: "Log out" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/login"));
    expect(getAccessToken()).toBeNull();
    expect(sessionStorage.getItem("nexora.session")).toBeNull();
    expect(screen.queryByTestId("session-card")).not.toBeInTheDocument();
  });
});
