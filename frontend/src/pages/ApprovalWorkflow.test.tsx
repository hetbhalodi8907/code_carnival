import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { calls, mockFetch, renderApp, signIn, FINANCE_MANAGER, type MockReply } from "@/test/utils";
import type { CurrentUser } from "@/types/api";

const SUBMIT = "/api/v1/document-submissions";
const SUB_ID = "9d1c0000-0000-4000-8000-000000000001";
const DOC_ID = "5f6c1c0e-0000-4000-8000-00000000d0c1";

const EMPLOYEE: CurrentUser = {
  ...FINANCE_MANAGER,
  email: "kabir.sethi@nexora.example",
  full_name: "Kabir Sethi",
  roles: ["EMPLOYEE"],
  permissions: ["documents:read", "documents:submit", "employee:self_read"],
};
const CEO: CurrentUser = {
  ...FINANCE_MANAGER,
  email: "ishaan.malhotra@nexora.example",
  full_name: "Ishaan Malhotra",
  roles: ["SUPER_ADMIN"],
  permissions: ["documents:read", "documents:write", "documents:submit", "documents:approve", "employee:self_read"],
};
const NO_SUBMIT: CurrentUser = { ...EMPLOYEE, permissions: ["documents:read", "employee:self_read"] };

function submission(over: Record<string, unknown> = {}) {
  return {
    id: SUB_ID, filename: "Budget.pdf", source_type: "pdf", mime_type: "application/pdf", size_bytes: 20480, page_count: 3,
    image_width: null, image_height: null, status: "pending_approval", created_at: "2026-10-10T09:30:00Z", updated_at: "2026-10-10T09:30:00Z",
    decided_at: null, rejection_reason: null, failure_message: null, attempts: 0, document_id: null, preview_available: true, submitter: null,
    ...over,
  };
}
const queued = (over: Record<string, unknown> = {}) => submission({ submitter: { name: "Kabir Sethi", email: "kabir.sethi@nexora.example" }, ...over });
const list = (...items: unknown[]): MockReply => ({ body: { submissions: items } });
const failure = (status: number, message: string): MockReply => ({ status, body: { error: { code: "HTTP_ERROR", message, request_id: "r" } } });

function file(name: string, type: string, size = 2048) {
  const f = new File(["bytes"], name, { type });
  Object.defineProperty(f, "size", { value: size });
  return f;
}
const as = (account: CurrentUser) => ({ "GET /api/v1/auth/me": { body: account } });

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:preview") as never;
  URL.revokeObjectURL = vi.fn() as never;
});

describe("submitting for approval (accounts without direct upload)", () => {
  it("submits a PDF to the review endpoint, never the direct-ingest one, and explains it is not searchable yet", async () => {
    signIn();
    let mine: unknown[] = [];
    const fetchMock = mockFetch({
      ...as(EMPLOYEE),
      [`GET ${SUBMIT}/mine`]: () => list(...mine),
      [`POST ${SUBMIT}`]: () => {
        mine = [submission()];
        return { status: 201, body: submission() };
      },
    });
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload");

    await user.upload(await screen.findByLabelText(/choose a file/i), file("Budget.pdf", "application/pdf"));
    expect(screen.getByTestId("selected-file")).toHaveTextContent("Budget.pdf");
    await user.click(screen.getByRole("button", { name: "Submit for approval" }));

    const received = await screen.findByTestId("submission-received");
    expect(received).toHaveTextContent("Submitted for approval");
    expect(received).toHaveTextContent("Pending approval");
    expect(received).toHaveTextContent("It will not be searchable until the CEO approves it and indexing finishes");
    expect(received).toHaveTextContent("10 Oct 2026"); // the submission timestamp
    const rows = await screen.findAllByTestId("submission-row");
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent("Budget.pdf");
    expect(rows[0]).toHaveTextContent("Pending approval");
    expect(within(rows[0]).queryByRole("button", { name: /Chat with this document/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Ready to search")).not.toBeInTheDocument();
    expect(calls(fetchMock, "POST", SUBMIT)).toHaveLength(1);
    expect(calls(fetchMock, "POST", "/api/v1/documents/ingest")).toHaveLength(0);
    expect(calls(fetchMock, "POST", "/api/v1/documents/ingest-image")).toHaveLength(0);
    const body = calls(fetchMock, "POST", SUBMIT)[0][1]?.body as FormData;
    expect((body.get("file") as File).name).toBe("Budget.pdf");
  });

  it("submits an image from the image page", async () => {
    signIn();
    const fetchMock = mockFetch({
      ...as(EMPLOYEE),
      [`GET ${SUBMIT}/mine`]: list(),
      [`POST ${SUBMIT}`]: { status: 201, body: submission({ filename: "notice.png", source_type: "image", mime_type: "image/png", page_count: null, image_width: 800, image_height: 600 }) },
    });
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload-image");
    await user.upload(await screen.findByLabelText(/choose a file/i), file("notice.png", "image/png"));
    await user.click(screen.getByRole("button", { name: "Submit for approval" }));
    expect(await screen.findByTestId("submission-received")).toHaveTextContent("notice.png");
    expect(calls(fetchMock, "POST", SUBMIT)).toHaveLength(1);
  });

  it("rejects an unsuitable file before any request and shows the server's reason when it refuses one", async () => {
    signIn();
    const fetchMock = mockFetch({
      ...as(EMPLOYEE),
      [`GET ${SUBMIT}/mine`]: list(),
      [`POST ${SUBMIT}`]: failure(422, "The uploaded file is not a valid PDF."),
    });
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload");
    await user.upload(await screen.findByLabelText(/choose a file/i), file("notes.txt", "text/plain"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only PDF files are supported.");
    expect(calls(fetchMock, "POST", SUBMIT)).toHaveLength(0);

    await user.upload(screen.getByLabelText(/choose a file/i), file("Broken.pdf", "application/pdf"));
    await user.click(screen.getByRole("button", { name: "Submit for approval" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The uploaded file is not a valid PDF.");
    expect(screen.queryByTestId("submission-received")).not.toBeInTheDocument();
  });

  it("shows the limit message when too many submissions are waiting", async () => {
    signIn();
    mockFetch({ ...as(EMPLOYEE), [`GET ${SUBMIT}/mine`]: list(), [`POST ${SUBMIT}`]: failure(429, "You have too many submissions awaiting review. Wait for a decision before submitting more.") });
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload");
    await user.upload(await screen.findByLabelText(/choose a file/i), file("Budget.pdf", "application/pdf"));
    await user.click(screen.getByRole("button", { name: "Submit for approval" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("too many submissions");
  });

  it("shows every status in words, the reason for a rejection, and chat only for a ready document", async () => {
    signIn();
    const fetchMock = mockFetch({
      ...as(EMPLOYEE),
      [`GET ${SUBMIT}/mine`]: list(
        submission({ id: "a1", filename: "waiting.pdf" }),
        submission({ id: "a2", filename: "working.pdf", status: "indexing" }),
        submission({ id: "a3", filename: "dropped.pdf", status: "rejected", rejection_reason: "Contains personal data", preview_available: false }),
        submission({ id: "a4", filename: "broken.pdf", status: "failed", failure_message: "The document's text could not be indexed. Try again." }),
        submission({ id: "a5", filename: "done.pdf", status: "ready", document_id: DOC_ID, preview_available: false }),
      ),
      [`POST /api/v1/assistant/document-query`]: { body: { status: "answered", answer: "It says [S1].", request_id: "r", sources: [], unverified_source_numbers: [], rejected_source_numbers: [], citation_check: "none", trust_proof: null } },
    });
    const user = userEvent.setup();
    renderApp("/app/upload");

    const rows = await screen.findAllByTestId("submission-row");
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining("Pending approval"),
      expect.stringContaining("Approved · Indexing"),
      expect.stringContaining("Rejected"),
      expect.stringContaining("Failed"),
      expect.stringContaining("Ready to search"),
    ]);
    expect(rows[2]).toHaveTextContent("Reason: Contains personal data");
    expect(rows[3]).toHaveTextContent("could not be indexed");
    const chatButtons = screen.getAllByRole("button", { name: /Chat with this document/ });
    expect(chatButtons).toHaveLength(1); // only the ready one
    expect(rows[4]).toContainElement(chatButtons[0]);

    await user.click(chatButtons[0]);
    const chat = await screen.findByTestId("document-chat");
    expect(chat).toHaveTextContent("done.pdf");
    await user.type(within(chat).getByLabelText("Ask about this document"), "Summarize it");
    await user.click(within(chat).getByRole("button", { name: "Send document question" }));
    await screen.findByText(/It says/);
    const asked = JSON.parse(String(calls(fetchMock, "POST", "/api/v1/assistant/document-query")[0][1]?.body));
    expect(asked.document_id).toBe(DOC_ID); // the active document's ID, never the submission's
  });

  it("shows only what the server returns for this account (nobody else's submissions)", async () => {
    signIn();
    mockFetch({ ...as(EMPLOYEE), [`GET ${SUBMIT}/mine`]: list(submission({ filename: "mine.pdf" })) });
    renderApp("/app/upload");
    expect(await screen.findByText("mine.pdf")).toBeInTheDocument();
    expect(screen.queryByText(/Submitted by/)).not.toBeInTheDocument();
  });

  it("keeps the locked page for an account with neither permission", async () => {
    signIn();
    const fetchMock = mockFetch(as(NO_SUBMIT));
    renderApp("/app/upload");
    expect(await screen.findByTestId("upload-locked")).toBeInTheDocument();
    expect(calls(fetchMock, "GET", `${SUBMIT}/mine`)).toHaveLength(0);
  });
});

describe("the CEO's approval queue", () => {
  const queueRoute = (...items: unknown[]) => ({ [`GET ${SUBMIT}/queue`]: list(...items) });

  it("is listed in the sidebar for the approver", async () => {
    signIn();
    mockFetch({ ...as(CEO), ...queueRoute() });
    renderApp("/app/approvals");
    const nav = await screen.findByRole("navigation", { name: "Sections" });
    expect(within(nav).getByRole("link", { name: "Approvals" })).toHaveAttribute("aria-current", "page");
  });

  it("is not listed for a submitter, and opening it directly shows an explanation and makes no queue request", async () => {
    signIn();
    const fetchMock = mockFetch({ ...as(EMPLOYEE), ...queueRoute(queued()), "GET /api/v1/dashboard/overview": failure(503, "x") });
    renderApp("/app/approvals");
    expect(await screen.findByTestId("approvals-restricted")).toHaveTextContent("limited to the CEO / Super Admin account");
    const nav = screen.getByRole("navigation", { name: "Sections" });
    expect(within(nav).queryByRole("link", { name: "Approvals" })).not.toBeInTheDocument();
    expect(calls(fetchMock, "GET", `${SUBMIT}/queue`)).toHaveLength(0);
    expect(screen.queryByText("Budget.pdf")).not.toBeInTheDocument();
  });

  it("lists pending submissions with who, when, size and safe metadata", async () => {
    signIn();
    mockFetch({ ...as(CEO), ...queueRoute(queued(), queued({ id: "b2", filename: "notice.png", source_type: "image", mime_type: "image/png", page_count: null, image_width: 800, image_height: 600, size_bytes: 123456 })) });
    renderApp("/app/approvals");
    const items = await screen.findAllByTestId("queue-item");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Budget.pdf");
    expect(items[0]).toHaveTextContent("PDF · 20 KB · 3 pages");
    expect(items[0]).toHaveTextContent("Kabir Sethi (kabir.sethi@nexora.example)");
    expect(items[0]).toHaveTextContent("10 Oct 2026");
    expect(items[0]).toHaveTextContent("Pending approval");
    expect(items[1]).toHaveTextContent("Image · 121 KB · 800×600 px");
    expect(screen.getByRole("heading", { level: 2, name: "Document Approval Queue" })).toBeInTheDocument();
  });

  it("shows an empty state and a retryable error", async () => {
    signIn();
    let n = 0;
    mockFetch({ ...as(CEO), [`GET ${SUBMIT}/queue`]: () => (++n === 1 ? failure(503, "db down postgresql://x") : list()) });
    const user = userEvent.setup();
    renderApp("/app/approvals");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Service temporarily unavailable");
    expect(document.body.textContent).not.toContain("postgresql://");
    await user.click(screen.getByRole("button", { name: "Refresh the queue" }));
    expect(await screen.findByText("No submissions are waiting for review.")).toBeInTheDocument();
  });

  it("previews a PDF and an image through the authenticated endpoint only", async () => {
    signIn();
    const fetchMock = mockFetch({
      ...as(CEO),
      ...queueRoute(queued(), queued({ id: "b2", filename: "notice.png", source_type: "image", mime_type: "image/png", page_count: null })),
      [`GET ${SUBMIT}/${SUB_ID}/preview`]: () => new Response(new Blob(["%PDF"], { type: "application/pdf" })) as never,
      [`GET ${SUBMIT}/b2/preview`]: () => new Response(new Blob(["png"], { type: "image/png" })) as never,
    });
    const user = userEvent.setup();
    renderApp("/app/approvals");
    const [pdfItem, imageItem] = await screen.findAllByTestId("queue-item");

    await user.click(within(pdfItem).getByRole("button", { name: "Preview" }));
    const frame = await within(pdfItem).findByTitle("Preview of Budget.pdf");
    expect(frame).toHaveAttribute("src", "blob:preview");
    const [, init] = calls(fetchMock, "GET", `${SUBMIT}/${SUB_ID}/preview`)[0];
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer test-access-token"); // not a public URL

    await user.click(within(imageItem).getByRole("button", { name: "Preview" }));
    expect(await within(imageItem).findByAltText("Preview of notice.png")).toHaveAttribute("src", "blob:preview");
    await user.click(within(pdfItem).getByRole("button", { name: "Hide preview" }));
    expect(within(pdfItem).queryByTitle("Preview of Budget.pdf")).not.toBeInTheDocument();
    expect(URL.revokeObjectURL).toHaveBeenCalled(); // the temporary URL is released
  });

  it("approves once: shows indexing work, then Ready to search, and a double click sends one request", async () => {
    signIn();
    let release: ((reply: MockReply) => void) | undefined;
    const fetchMock = mockFetch({
      ...as(CEO),
      ...queueRoute(queued()),
      [`POST ${SUBMIT}/${SUB_ID}/approve`]: () => new Promise<MockReply>((resolve) => (release = resolve)),
    });
    const user = userEvent.setup();
    renderApp("/app/approvals");
    const item = await screen.findByTestId("queue-item");

    const approve = within(item).getByRole("button", { name: "Approve" });
    await user.dblClick(approve);
    expect(await within(item).findByRole("button", { name: "Approving and indexing…" })).toBeDisabled();
    expect(within(item).queryByText("Ready to search")).not.toBeInTheDocument(); // not before the server says so
    release?.({ body: queued({ status: "ready", document_id: DOC_ID, preview_available: false, attempts: 1 }) });

    expect(await within(item).findByText("Ready to search")).toBeInTheDocument();
    expect(item).toHaveTextContent("searchable only by the person who submitted it");
    expect(within(item).queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(calls(fetchMock, "POST", `${SUBMIT}/${SUB_ID}/approve`)).toHaveLength(1);
  });

  it("shows a failed approval as failed with a safe message and lets the CEO retry", async () => {
    signIn();
    let attempt = 0;
    mockFetch({
      ...as(CEO),
      ...queueRoute(queued()),
      [`POST ${SUBMIT}/${SUB_ID}/approve`]: () =>
        ++attempt === 1
          ? { body: queued({ status: "failed", failure_message: "The document's text could not be indexed. Try again.", attempts: 1 }) }
          : { body: queued({ status: "ready", document_id: DOC_ID, preview_available: false, attempts: 2 }) },
    });
    const user = userEvent.setup();
    renderApp("/app/approvals");
    const item = await screen.findByTestId("queue-item");
    await user.click(within(item).getByRole("button", { name: "Approve" }));

    expect(await within(item).findByText("Failed")).toBeInTheDocument();
    expect(item).toHaveTextContent("could not be indexed");
    expect(item).toHaveTextContent("Nothing was indexed; you can retry");
    expect(within(item).queryByText("Ready to search")).not.toBeInTheDocument();
    await user.click(within(item).getByRole("button", { name: "Retry approval" }));
    expect(await within(item).findByText("Ready to search")).toBeInTheDocument();
  });

  it("rejects with an optional reason and shows the result without a searchable state", async () => {
    signIn();
    const fetchMock = mockFetch({
      ...as(CEO),
      ...queueRoute(queued()),
      [`POST ${SUBMIT}/${SUB_ID}/reject`]: { body: queued({ status: "rejected", rejection_reason: "Contains personal data", preview_available: false }) },
    });
    const user = userEvent.setup();
    renderApp("/app/approvals");
    const item = await screen.findByTestId("queue-item");
    await user.click(within(item).getByRole("button", { name: "Reject" }));
    await user.type(within(item).getByLabelText("Reason (optional)"), "Contains personal data");
    await user.click(within(item).getByRole("button", { name: "Confirm rejection" }));

    expect(await within(item).findByText("Rejected")).toBeInTheDocument();
    expect(item).toHaveTextContent("Reason: Contains personal data");
    expect(item).toHaveTextContent("The file was deleted and nothing was indexed");
    expect(within(item).queryByText("Ready to search")).not.toBeInTheDocument();
    expect(JSON.parse(String(calls(fetchMock, "POST", `${SUBMIT}/${SUB_ID}/reject`)[0][1]?.body))).toEqual({ reason: "Contains personal data" });
  });

  it("reports a conflict (already processed) in the server's words instead of pretending it worked", async () => {
    signIn();
    mockFetch({ ...as(CEO), ...queueRoute(queued()), [`POST ${SUBMIT}/${SUB_ID}/approve`]: failure(409, "This submission is already being processed.") });
    const user = userEvent.setup();
    renderApp("/app/approvals");
    const item = await screen.findByTestId("queue-item");
    await user.click(within(item).getByRole("button", { name: "Approve" }));
    expect(await within(item).findByText("This submission is already being processed.")).toBeInTheDocument();
    expect(within(item).queryByText("Ready to search")).not.toBeInTheDocument();
    await waitFor(() => expect(within(item).getByRole("button", { name: "Approve" })).toBeEnabled());
  });
});

describe("dashboard shortcuts", () => {
  it("offers the upload pages to submitters and the approval queue only to the approver", async () => {
    for (const [account, expectsApprovals] of [[EMPLOYEE, false], [CEO, true]] as const) {
      signIn();
      mockFetch({
        ...as(account),
        "GET /api/v1/dashboard/overview": {
          body: {
            generated_at: "2026-10-10T08:30:00Z", dataset_note: "Demo dataset", variant: account === CEO ? "ceo" : "employee",
            user: { id: "u", full_name: account.full_name, email: account.email, roles: account.roles, department: null },
            documents: { total: 0, by_status: [], by_source_type: [], fully_indexed: 0, chunks_total: 0, chunks_embedded: 0, recent: [] },
            my_work: { projects: [], upcoming_milestones: [] }, projects: null, finance: null, workforce: null, security: null, unavailable: [],
          },
        },
      });
      renderApp("/app/dashboard");
      const shortcuts = await screen.findByRole("navigation", { name: "Shortcuts" });
      expect(within(shortcuts).getByRole("link", { name: "Upload a PDF" })).toBeInTheDocument();
      expect(within(shortcuts).queryByRole("link", { name: "Approval queue" }) !== null).toBe(expectsApprovals);
      document.body.innerHTML = "";
    }
  });
});
