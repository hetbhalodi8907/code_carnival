import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { CurrentUser } from "@/types/api";
import { FINANCE_MANAGER, calls, mockFetch, renderApp, signIn } from "@/test/utils";

/** Accounts holding NEITHER documents:write nor documents:submit (no real demo role is like this since the approval workflow). */
const USERS: Record<string, CurrentUser> = {
  "Finance Manager": FINANCE_MANAGER,
  "HR Manager": {
    ...FINANCE_MANAGER,
    email: "meera.iyer@nexora.example",
    full_name: "Meera Iyer",
    roles: ["HR_MANAGER"],
    permissions: ["documents:read", "employee:self_read", "hr:read", "hr:write"],
  },
  Employee: {
    ...FINANCE_MANAGER,
    email: "kabir.sethi@nexora.example",
    full_name: "Kabir Sethi",
    roles: ["EMPLOYEE"],
    permissions: ["documents:read", "employee:self_read"],
  },
};
const ADMIN: CurrentUser = {
  ...FINANCE_MANAGER,
  email: "ishaan.malhotra@nexora.example",
  full_name: "Ishaan Malhotra",
  roles: ["SUPER_ADMIN"],
  permissions: ["documents:read", "documents:write", "documents:submit", "documents:approve", "hr:read", "finance:read"],
};

/** The demo roles as the server reports them now: every role may submit; only SUPER_ADMIN may write and approve. */
const SUBMITTERS: Record<string, CurrentUser> = Object.fromEntries(
  Object.entries(USERS).map(([label, account]) => [label, { ...account, permissions: [...account.permissions, "documents:submit"] }]),
);

const PAGES = [
  { path: "/app/upload", link: "Upload", noun: "PDFs", name: "Upload" },
  { path: "/app/upload-image", link: "Upload images", noun: "images", name: "Upload images" },
] as const;

describe("upload navigation and locked state", () => {
  describe.each(Object.entries(USERS))("%s (no documents:submit and no documents:write)", (_label, account) => {
    it("sees both upload entries marked as locked", async () => {
      signIn();
      mockFetch({ "GET /api/v1/auth/me": { body: account } });
      renderApp("/app/chat");

      const nav = await screen.findByRole("navigation", { name: "Sections" });
      for (const { link } of PAGES) {
        const entry = within(nav).getByRole("link", { name: new RegExp(`^${link} \\(locked: requires the documents:submit permission\\)$`) });
        expect(entry).toHaveAttribute("title", "Requires the documents:submit permission");
      }
      expect(within(nav).getByRole("link", { name: "Assistant" })).toBeInTheDocument();
    });

    it.each(PAGES)("opens $path from the sidebar to an explanation, with no upload control and no request", async ({ link, noun }) => {
      signIn();
      const fetchMock = mockFetch({ "GET /api/v1/auth/me": { body: account } });
      const user = userEvent.setup();
      renderApp("/app/chat");

      await user.click(await screen.findByRole("link", { name: new RegExp(`^${link} \\(locked`) }));

      const locked = await screen.findByTestId("upload-locked");
      expect(locked).toHaveTextContent("Uploading isn't available for your account");
      expect(locked).toHaveTextContent(`Submitting ${noun} requires the documents:submit permission`);
      // Nothing to upload with: no file input, no dropzone and no submit button.
      expect(document.querySelector("input[type=file]")).toBeNull();
      expect(screen.queryByLabelText(/choose a file/i)).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /^Upload and/ })).not.toBeInTheDocument();
      expect(calls(fetchMock, "POST", "/api/v1/documents/ingest")).toHaveLength(0);
      expect(calls(fetchMock, "POST", "/api/v1/documents/ingest-image")).toHaveLength(0);

      // A way back to the chat.
      await user.click(within(locked).getByRole("link", { name: "Back to the assistant" }));
      expect(screen.getByTestId("location")).toHaveTextContent("/app/chat");
    });

    it.each(PAGES)("shows the locked page, not a blank screen, when $path is opened directly", async ({ path }) => {
      signIn();
      mockFetch({ "GET /api/v1/auth/me": { body: account } });
      renderApp(path);

      expect(await screen.findByTestId("upload-locked")).toBeInTheDocument();
      expect(screen.getByTestId("location")).toHaveTextContent(path);
    });
  });

  describe.each(Object.entries(SUBMITTERS))("%s (documents:submit, no documents:write)", (_label, account) => {
    it("sees both upload entries unlocked and the submit-for-approval page, never a direct-ingest form", async () => {
      signIn();
      const fetchMock = mockFetch({ "GET /api/v1/auth/me": { body: account }, "GET /api/v1/document-submissions/mine": { body: { submissions: [] } } });
      const user = userEvent.setup();
      renderApp("/app/chat");

      const nav = await screen.findByRole("navigation", { name: "Sections" });
      expect(nav).not.toHaveTextContent("locked");
      expect(within(nav).queryByRole("link", { name: "Approvals" })).not.toBeInTheDocument(); // reviewing is the CEO's alone

      for (const { link, path } of PAGES) {
        await user.click(within(nav).getByRole("link", { name: link }));
        expect(await screen.findByTestId("review-upload-page")).toBeInTheDocument();
        expect(screen.getByTestId("location")).toHaveTextContent(path);
        expect(screen.getByLabelText(/choose a file/i)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Submit for approval" })).toBeDisabled(); // until a file is chosen
        expect(screen.queryByRole("button", { name: /^Upload and/ })).not.toBeInTheDocument();
        expect(await screen.findByText("My submissions")).toBeInTheDocument();
        expect(screen.queryByTestId("upload-locked")).not.toBeInTheDocument();
      }
      expect(calls(fetchMock, "POST", "/api/v1/documents/ingest")).toHaveLength(0);
      expect(calls(fetchMock, "POST", "/api/v1/documents/ingest-image")).toHaveLength(0);
    });
  });

  describe("CEO / Super Admin (documents:write)", () => {
    it("sees both entries unlocked and gets the working upload forms", async () => {
      signIn();
      mockFetch({ "GET /api/v1/auth/me": { body: ADMIN } });
      const user = userEvent.setup();
      renderApp("/app/chat");

      const nav = await screen.findByRole("navigation", { name: "Sections" });
      for (const { name } of PAGES) {
        const entry = within(nav).getByRole("link", { name });
        expect(entry).not.toHaveAttribute("title");
      }
      expect(nav).not.toHaveTextContent("locked");

      await user.click(within(nav).getByRole("link", { name: "Upload" }));
      expect(await screen.findByLabelText(/choose a file/i)).toBeInTheDocument();
      expect(screen.queryByTestId("upload-locked")).not.toBeInTheDocument();

      await user.click(within(nav).getByRole("link", { name: "Upload images" }));
      expect(await screen.findByLabelText(/choose a file/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Upload and read" })).toBeDisabled(); // until a file is chosen
      expect(screen.queryByTestId("upload-locked")).not.toBeInTheDocument();
    });
  });

  it("never renders a page for a signed-out visitor, so permissions cannot flash while loading", async () => {
    mockFetch({});
    renderApp("/app/upload");
    expect(await screen.findByRole("heading", { name: /Log in/i })).toBeInTheDocument();
    expect(screen.queryByTestId("upload-locked")).not.toBeInTheDocument();
    expect(document.querySelector("input[type=file]")).toBeNull();
  });
});
