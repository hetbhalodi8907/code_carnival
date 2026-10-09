import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { getAccessToken } from "@/services/session";
import type { CurrentUser, DocumentIngestionResponse, EmbeddingStorageResponse } from "@/types/api";
import { FINANCE_MANAGER, calls, mockFetch, renderApp, signIn, type MockReply } from "@/test/utils";

const ADMIN: CurrentUser = {
  ...FINANCE_MANAGER,
  email: "ishaan.malhotra@nexora.example",
  full_name: "Ishaan Malhotra",
  roles: ["SUPER_ADMIN"],
  permissions: ["documents:read", "documents:write", "finance:read"],
};
const ME = { "GET /api/v1/auth/me": { body: ADMIN } };

const INGEST = "/api/v1/documents/ingest";
const DOC_ID = "5f6c1c0e-0000-4000-8000-00000000abcd";
const EMBED = `/api/v1/embeddings/documents/${DOC_ID}`;

const MODEL = "sentence-transformers/all-MiniLM-L6-v2";
const STORED: DocumentIngestionResponse = {
  document_id: DOC_ID,
  filename: "Policy.pdf",
  source_type: "pdf",
  source_path: `${DOC_ID}.pdf`,
  page_count: 3,
  chunk_count: 7,
  status: "processed",
};
/** What the updated backend returns: stored AND indexed in the one request. */
const INGESTED: DocumentIngestionResponse = { ...STORED, embedding_status: "completed", embedding_model: MODEL };
const notIndexed = (embedding_status: string | null | undefined, embedding_model: string | null = null) => ({
  ...STORED,
  ...(embedding_status === undefined ? {} : { embedding_status }),
  embedding_model,
});
const EMBEDDED: EmbeddingStorageResponse = {
  document_id: DOC_ID,
  chunks_processed: 7,
  embeddings_created: 7,
  embedding_model: MODEL,
  status: "completed",
};

function error(status: number, message = "server detail"): MockReply {
  return { status, body: { error: { code: "HTTP_ERROR", message, request_id: "r" } } };
}

function pdf(name = "Policy.pdf", size = 2048, type = "application/pdf") {
  const file = new File(["%PDF-1.7 test"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

async function open() {
  signIn();
  const user = userEvent.setup({ applyAccept: false });
  renderApp("/app/upload");
  await screen.findByRole("heading", { level: 2, name: "Upload Documents" });
  return user;
}

const input = () => screen.getByLabelText(/choose a file/i);
const submit = () => screen.getByRole("button", { name: /Upload and index|Uploading|Indexing/ });

describe("upload page", () => {
  it("is offered only to accounts the server reports with documents:write", async () => {
    signIn();
    mockFetch(ME);
    renderApp("/app/chat");
    expect(await screen.findByRole("link", { name: "Upload" })).toBeInTheDocument();
  });

  it("hides the link and the form from an account without documents:write", async () => {
    signIn();
    mockFetch({ "GET /api/v1/auth/me": { body: FINANCE_MANAGER } });
    renderApp("/app/upload");

    expect(await screen.findByText("Uploading isn't available for your account")).toBeInTheDocument();
    expect(screen.queryByLabelText(/choose a file/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Upload" })).not.toBeInTheDocument();
  });

  it("rejects non-PDF, empty, oversized and multiple files before any request", async () => {
    signIn();
    const fetchMock = mockFetch(ME);
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload");
    await screen.findByRole("heading", { level: 2, name: "Upload Documents" });

    await user.upload(input(), pdf("notes.txt", 100, "text/plain"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only PDF files are supported.");

    await user.upload(input(), pdf("empty.pdf", 0));
    expect(screen.getByRole("alert")).toHaveTextContent("This PDF is empty.");

    await user.upload(input(), pdf("big.pdf", 26 * 1024 * 1024));
    expect(screen.getByRole("alert")).toHaveTextContent("This file is 26.0 MB. PDFs must be no larger than 25 MB.");

    fireEvent.drop(input().closest("label")!, { dataTransfer: { files: [pdf("a.pdf"), pdf("b.pdf")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Upload one PDF at a time.");

    expect(screen.queryByTestId("selected-file")).not.toBeInTheDocument();
    expect(calls(fetchMock, "POST", INGEST)).toHaveLength(0);
  });

  it("shows the chosen file's name and size and lets it be removed", async () => {
    mockFetch(ME);
    const user = await open();

    await user.upload(input(), pdf("Quarterly Report.pdf", 1_500_000));

    const selected = screen.getByTestId("selected-file");
    expect(selected).toHaveTextContent("Quarterly Report.pdf");
    expect(selected).toHaveTextContent("1.4 MB");
    expect(submit()).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Remove selected file" }));
    expect(screen.queryByTestId("selected-file")).not.toBeInTheDocument();
    expect(submit()).toBeDisabled();
  });

  it("accepts a dropped PDF", async () => {
    signIn();
    mockFetch(ME);
    renderApp("/app/upload");
    await screen.findByRole("heading", { level: 2, name: "Upload Documents" });

    fireEvent.drop(input().closest("label")!, { dataTransfer: { files: [pdf("Dropped.pdf")] } });

    expect(await screen.findByTestId("selected-file")).toHaveTextContent("Dropped.pdf");
  });

  it("uploads once as multipart with the bearer token and is ready without a second API call", async () => {
    signIn();
    let releaseUpload: (reply: MockReply) => void = () => {};
    const fetchMock = mockFetch({
      ...ME,
      [`POST ${INGEST}`]: () => new Promise<MockReply>((resolve) => (releaseUpload = resolve)),
      [`POST ${EMBED}`]: { body: EMBEDDED },
    });
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload");
    await screen.findByRole("heading", { level: 2, name: "Upload Documents" });
    await user.upload(input(), pdf("Policy.pdf"));

    await user.click(submit());

    // While the single request runs, nothing is claimed about searchability.
    expect(await screen.findByText("Uploading, extracting text and indexing…")).toBeInTheDocument();
    expect(screen.queryByTestId("upload-ready")).not.toBeInTheDocument();
    expect(submit()).toBeDisabled();

    const [, init] = calls(fetchMock, "POST", INGEST)[0];
    const headers = init?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer test-access-token");
    expect(headers["Content-Type"]).toBeUndefined();
    expect(init?.body).toBeInstanceOf(FormData);
    expect((init?.body as FormData).get("file")).toMatchObject({ name: "Policy.pdf" });

    releaseUpload({ status: 201, body: INGESTED });
    const ready = await screen.findByTestId("upload-ready");
    expect(ready).toHaveTextContent("Ready to search");
    expect(ready).toHaveTextContent(`Policy.pdf was stored (3 pages, 7 text passages) and indexed with ${MODEL}.`);
    expect(within(ready).getByRole("link", { name: "Ask the assistant" })).toHaveAttribute("href", "/app/chat");
    // Exactly one upload and no separate embedding request.
    expect(calls(fetchMock, "POST", INGEST)).toHaveLength(1);
    expect(calls(fetchMock, "POST", EMBED)).toHaveLength(0);
    expect(screen.queryByTestId("selected-file")).not.toBeInTheDocument();
  });

  it("opens the assistant from the success state", async () => {
    signIn();
    mockFetch({ ...ME, [`POST ${INGEST}`]: { status: 201, body: INGESTED } });
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload");
    await screen.findByRole("heading", { level: 2, name: "Upload Documents" });
    await user.upload(input(), pdf());
    await user.click(submit());

    await user.click(await screen.findByRole("link", { name: "Ask the assistant" }));

    expect(await screen.findByRole("heading", { level: 2, name: "Enterprise Assistant" })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/app/chat");
  });

  it("shows the server's validation message and never indexes when the upload is rejected", async () => {
    signIn();
    const fetchMock = mockFetch({ ...ME, [`POST ${INGEST}`]: error(422, "The uploaded file is not a valid PDF.") });
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload");
    await screen.findByRole("heading", { level: 2, name: "Upload Documents" });
    await user.upload(input(), pdf());

    await user.click(submit());

    expect(await screen.findByRole("alert")).toHaveTextContent("The uploaded file is not a valid PDF.");
    expect(screen.queryByTestId("upload-ready")).not.toBeInTheDocument();
    expect(calls(fetchMock, "POST", EMBED)).toHaveLength(0);
    // The file stays selected so the person can retry or choose another.
    expect(screen.getByTestId("selected-file")).toBeInTheDocument();
    expect(submit()).toBeEnabled();
  });

  it("maps 403, 413 and server errors to safe messages", async () => {
    signIn();
    let reply: MockReply = error(403, "Permission denied.");
    mockFetch({ ...ME, [`POST ${INGEST}`]: () => reply });
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload");
    await screen.findByRole("heading", { level: 2, name: "Upload Documents" });
    await user.upload(input(), pdf());

    await user.click(submit());
    expect(await screen.findByRole("alert")).toHaveTextContent("Upload not permitted");

    reply = error(413, "The PDF must be no larger than 25 MB.");
    await user.click(submit());
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("File too large"));
    expect(screen.getByRole("alert")).toHaveTextContent("The PDF must be no larger than 25 MB.");

    reply = error(500, "Traceback: /srv/app/ingest.py line 9");
    await user.click(submit());
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Upload failed"));
    expect(document.body.textContent).not.toContain("Traceback");
  });

  it.each([
    ["failed", notIndexed("failed"), "The server reported that indexing failed."],
    ["not_configured", notIndexed("not_configured"), "The server reported that the embedding service is not configured."],
    ["missing", notIndexed(undefined), "The server did not confirm that indexing completed."],
    ["null", notIndexed(null), "The server did not confirm that indexing completed."],
    ["unrecognized", notIndexed("pending"), "The server did not confirm that indexing completed."],
    ["completed without a model", notIndexed("completed"), "The server did not confirm that indexing completed."],
  ])("never shows Ready to search when indexing is %s", async (_label, body, explanation) => {
    signIn();
    const fetchMock = mockFetch({ ...ME, [`POST ${INGEST}`]: { status: 201, body }, [`POST ${EMBED}`]: { body: EMBEDDED } });
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload");
    await screen.findByRole("heading", { level: 2, name: "Upload Documents" });
    await user.upload(input(), pdf());

    await user.click(submit());

    const notice = await screen.findByTestId("upload-index-failed");
    expect(notice).toHaveTextContent("Stored, but not searchable yet");
    expect(notice).toHaveTextContent(explanation);
    expect(notice).toHaveTextContent("Policy.pdf was stored (3 pages, 7 text passages)");
    expect(within(notice).getByRole("button", { name: "Retry indexing" })).toBeEnabled();
    expect(screen.queryByTestId("upload-ready")).not.toBeInTheDocument();
    expect(screen.queryByText("Ready to search")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Ask the assistant" })).not.toBeInTheDocument();
    // Nothing indexes automatically after a failed upload-time indexing.
    expect(calls(fetchMock, "POST", EMBED)).toHaveLength(0);
  });

  it("retries indexing for the stored document without uploading again, and is ready only after it succeeds", async () => {
    signIn();
    let embedReply: MockReply = error(503, "The embedding provider is not configured.");
    const fetchMock = mockFetch({
      ...ME,
      [`POST ${INGEST}`]: { status: 201, body: notIndexed("not_configured") },
      [`POST ${EMBED}`]: () => embedReply,
    });
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload");
    await screen.findByRole("heading", { level: 2, name: "Upload Documents" });
    await user.upload(input(), pdf());
    await user.click(submit());
    const first = await screen.findByTestId("upload-index-failed");

    // A failing retry keeps the honest state and the same document.
    await user.click(within(first).getByRole("button", { name: "Retry indexing" }));
    await waitFor(() =>
      expect(screen.getByTestId("upload-index-failed")).toHaveTextContent("The embedding service isn't configured on the server"),
    );
    expect(screen.getByTestId("upload-index-failed")).toHaveTextContent("Stored, but not searchable yet");
    expect(screen.queryByTestId("upload-ready")).not.toBeInTheDocument();

    embedReply = { body: EMBEDDED };
    await user.click(within(screen.getByTestId("upload-index-failed")).getByRole("button", { name: "Retry indexing" }));

    const ready = await screen.findByTestId("upload-ready");
    expect(ready).toHaveTextContent("Ready to search");
    expect(ready).toHaveTextContent("7 passages were indexed");
    expect(calls(fetchMock, "POST", INGEST)).toHaveLength(1); // the PDF was never uploaded again
    const retries = calls(fetchMock, "POST", EMBED);
    expect(retries).toHaveLength(2);
    expect(retries.every(([url]) => String(url).endsWith(`/embeddings/documents/${DOC_ID}`))).toBe(true);
    expect((retries[0][1]?.headers as Record<string, string>).Authorization).toBe("Bearer test-access-token");
  });

  it("returns to the login page when the session expires during a retry", async () => {
    signIn();
    mockFetch({
      ...ME,
      [`POST ${INGEST}`]: { status: 201, body: notIndexed("failed") },
      [`POST ${EMBED}`]: error(401, "expired"),
    });
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload");
    await screen.findByRole("heading", { level: 2, name: "Upload Documents" });
    await user.upload(input(), pdf());
    await user.click(submit());

    await user.click(await screen.findByRole("button", { name: "Retry indexing" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/login"));
    expect(getAccessToken()).toBeNull();
  });

  it("treats an unexpected or incomplete response as a failure, never as success", async () => {
    signIn();
    mockFetch({ ...ME, [`POST ${INGEST}`]: { status: 201, body: { filename: "Policy.pdf", status: "processed" } } });
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload");
    await screen.findByRole("heading", { level: 2, name: "Upload Documents" });
    await user.upload(input(), pdf());

    await user.click(submit());

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.queryByTestId("upload-ready")).not.toBeInTheDocument();
  });

  it("does not report success when a retry response does not confirm indexing", async () => {
    signIn();
    mockFetch({
      ...ME,
      [`POST ${INGEST}`]: { status: 201, body: notIndexed("failed") },
      [`POST ${EMBED}`]: { body: { ...EMBEDDED, embeddings_created: 0 } },
    });
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload");
    await screen.findByRole("heading", { level: 2, name: "Upload Documents" });
    await user.upload(input(), pdf());
    await user.click(submit());

    await user.click(await screen.findByRole("button", { name: "Retry indexing" }));

    await waitFor(() => expect(screen.getByTestId("upload-index-failed")).toHaveTextContent("The server returned an unexpected response."));
    expect(screen.getByTestId("upload-index-failed")).toHaveTextContent("Stored, but not searchable yet");
    expect(screen.queryByTestId("upload-ready")).not.toBeInTheDocument();
  });

  it("returns to the login page when the session expires during upload", async () => {
    signIn();
    mockFetch({ ...ME, [`POST ${INGEST}`]: error(401, "expired") });
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload");
    await screen.findByRole("heading", { level: 2, name: "Upload Documents" });
    await user.upload(input(), pdf());

    await user.click(submit());

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/login"));
    expect(getAccessToken()).toBeNull();
  });
});
