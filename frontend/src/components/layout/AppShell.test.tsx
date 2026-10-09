import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { getAccessToken } from "@/services/session";
import { FINANCE_MANAGER, mockFetch, renderApp, signIn } from "@/test/utils";

const ME = { "GET /api/v1/auth/me": { body: FINANCE_MANAGER } };

describe("application shell", () => {
  it("marks the current page in the sidebar and titles the top bar", async () => {
    signIn();
    mockFetch(ME);
    renderApp("/app/chat");

    expect(await screen.findByRole("heading", { level: 1, name: "Assistant" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Sections" });
    expect(within(nav).getByRole("link", { name: "Assistant" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Profile" })).not.toHaveAttribute("aria-current");
  });

  it("shows the server's identity in the sidebar and the role chip", async () => {
    signIn();
    mockFetch(ME);
    renderApp("/app/chat");

    const session = await screen.findByTestId("session-card");
    expect(session).toHaveTextContent("Vikram Nair");
    expect(session).toHaveTextContent("vikram.nair@nexora.example");
    expect(session).toHaveTextContent("4 server-granted permissions");
    expect(screen.getByTestId("current-user-role")).toHaveTextContent("Finance Manager");
  });

  it("opens the account menu, closes it with Escape and navigates to the profile", async () => {
    signIn();
    mockFetch(ME);
    const user = userEvent.setup();
    renderApp("/app/chat");

    const trigger = await screen.findByRole("button", { name: "Account menu" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    await user.click(trigger);
    const menu = screen.getByRole("menu");
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(menu).toHaveTextContent("vikram.nair@nexora.example");

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();

    await user.click(trigger);
    await user.click(screen.getByRole("menuitem", { name: "View profile" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Profile & session" })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/app/profile");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("logs out from the account menu", async () => {
    signIn();
    mockFetch(ME);
    const user = userEvent.setup();
    renderApp("/app/chat");

    await user.click(await screen.findByRole("button", { name: "Account menu" }));
    await user.click(screen.getByRole("menuitem", { name: "Log out" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/login"));
    expect(getAccessToken()).toBeNull();
  });

  it("opens the mobile navigation drawer and closes it with its button and with Escape", async () => {
    signIn();
    mockFetch(ME);
    const user = userEvent.setup();
    renderApp("/app/chat");

    const open = await screen.findByRole("button", { name: "Open navigation" });
    expect(open).toHaveAttribute("aria-expanded", "false");

    await user.click(open);
    expect(open).toHaveAttribute("aria-expanded", "true");
    await waitFor(() => expect(screen.getByRole("button", { name: "Close navigation" })).toHaveFocus());

    await user.click(screen.getByRole("button", { name: "Close navigation" }));
    expect(open).toHaveAttribute("aria-expanded", "false");

    await user.click(open);
    await user.keyboard("{Escape}");
    expect(open).toHaveAttribute("aria-expanded", "false");
    expect(open).toHaveFocus();
  });

  it("closes the drawer when a navigation link is chosen", async () => {
    signIn();
    mockFetch(ME);
    const user = userEvent.setup();
    renderApp("/app/chat");

    const open = await screen.findByRole("button", { name: "Open navigation" });
    await user.click(open);
    await user.click(within(screen.getByRole("navigation", { name: "Sections" })).getByRole("link", { name: "Profile" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Profile & session" })).toBeInTheDocument();
    expect(open).toHaveAttribute("aria-expanded", "false");
  });

  it("shows a loading message while a saved session is confirmed", async () => {
    signIn();
    mockFetch({ "GET /api/v1/auth/me": () => new Promise(() => {}) });
    renderApp("/app/chat");

    expect(await screen.findByRole("status")).toHaveTextContent("Restoring your secure session…");
  });
});
