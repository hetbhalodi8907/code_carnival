import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { getAccessToken } from "@/services/session";
import type { CurrentUser, EmbeddingStorageResponse, ImageIngestionResponse } from "@/types/api";
import { FINANCE_MANAGER, calls, mockFetch, renderApp, signIn, type MockReply } from "@/test/utils";

const ADMIN: CurrentUser = {
  ...FINANCE_MANAGER,
  email: "ishaan.malhotra@nexora.example",
  full_name: "Ishaan Malhotra",
  roles: ["SUPER_ADMIN"],
  permissions: ["documents:read", "documents:write", "finance:read"],
};
const ME = { "GET /api/v1/auth/me": { body: ADMIN } };

const INGEST_IMAGE = "/api/v1/documents/ingest-image";
const INGEST_PDF = "/api/v1/documents/ingest";
const DOC_ID = "9a1c1c0e-0000-4000-8000-00000000beef";
const EMBED = `/api/v1/embeddings/documents/${DOC_ID}`;

const INGESTED: ImageIngestionResponse = {
  document_id: DOC_ID,
  filename: "Notice.png",
  source_type: "image",
  source_path: `${DOC_ID}.png`,
  chunk_count: 2,
  ocr_line_count: 4,
  ocr_mean_confidence: 0.9819,
  embedding_status: "completed",
  status: "processed",
};
const EMBEDDED: EmbeddingStorageResponse = {
  document_id: DOC_ID,
  chunks_processed: 2,
  embeddings_created: 2,
  embedding_model: "sentence-transformers/all-MiniLM-L6-v2",
  status: "completed",
};

const created = (body: unknown): MockReply => ({ status: 201, body });
function error(status: number, message = "server detail"): MockReply {
  return { status, body: { error: { code: "HTTP_ERROR", message, request_id: "r" } } };
}

function image(name = "Notice.png", size = 4096, type = "image/png") {
  const file = new File(["fake image bytes"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

async function openPage(routes: Record<string, MockReply | (() => MockReply | Promise<MockReply>)> = {}) {
  signIn();
  const fetchMock = mockFetch({ ...ME, ...routes });
  const user = userEvent.setup({ applyAccept: false });
  renderApp("/app/upload-image");
  await screen.findByRole("heading", { level: 2, name: "Upload Images" });
  return { user, fetchMock };
}

const input = () => screen.getByLabelText(/choose a file/i);
const submit = () => screen.getByRole("button", { name: /Upload and read|Reading image|Indexing/ });
async function pick(user: ReturnType<typeof userEvent.setup>, file = image()) {
  await user.upload(input(), file);
}

describe("image upload page", () => {
  it("is offered only to accounts the server reports with documents:write", async () => {
    signIn();
    mockFetch(ME);
    renderApp("/app/chat");
    expect(await screen.findByRole("link", { name: "Upload images" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload" })).toBeInTheDocument();
  });

  it("shows an explanation, not the form or a link, to an account without documents:write", async () => {
    signIn();
    mockFetch({ "GET /api/v1/auth/me": { body: FINANCE_MANAGER } });
    renderApp("/app/upload-image");

    expect(await screen.findByText("Uploading isn't available for your account")).toBeInTheDocument();
    expect(screen.queryByLabelText(/choose a file/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Upload images \(locked/ })).toBeInTheDocument();
  });

  it("rejects unsupported, mismatched, empty, oversized and multiple files without any request", async () => {
    const { user, fetchMock } = await openPage();

    await user.upload(input(), image("scan.gif", 100, "image/gif"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only PNG and JPEG images are supported.");

    await user.upload(input(), image("scan.pdf", 100, "application/pdf"));
    expect(screen.getByRole("alert")).toHaveTextContent("Only PNG and JPEG images are supported.");

    await user.upload(input(), image("scan.png", 100, "image/jpeg"));
    expect(screen.getByRole("alert")).toHaveTextContent("type doesn't match its extension");

    await user.upload(input(), image("empty.png", 0));
    expect(screen.getByRole("alert")).toHaveTextContent("This image is empty.");

    await user.upload(input(), image("huge.jpg", 11 * 1024 * 1024, "image/jpeg"));
    expect(screen.getByRole("alert")).toHaveTextContent("This file is 11.0 MB. Images must be no larger than 10 MB.");

    fireEvent.drop(input().closest("label")!, { dataTransfer: { files: [image("a.png"), image("b.png")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Upload one image at a time.");

    expect(screen.queryByTestId("selected-file")).not.toBeInTheDocument();
    expect(calls(fetchMock, "POST", INGEST_IMAGE)).toHaveLength(0);
  });

  it("accepts PNG and JPEG (including .jpeg), shows name and size, and allows removal", async () => {
    const { user } = await openPage();

    await pick(user, image("Quarterly Scan.jpeg", 2_500_000, "image/jpeg"));
    const selected = screen.getByTestId("selected-file");
    expect(selected).toHaveTextContent("Quarterly Scan.jpeg");
    expect(selected).toHaveTextContent("2.4 MB");
    expect(submit()).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Remove selected file" }));
    expect(screen.queryByTestId("selected-file")).not.toBeInTheDocument();
    expect(submit()).toBeDisabled();
  });

  it("accepts a dropped image", async () => {
    await openPage();
    fireEvent.drop(input().closest("label")!, { dataTransfer: { files: [image("Dropped.png")] } });
    expect(await screen.findByTestId("selected-file")).toHaveTextContent("Dropped.png");
  });

  it("uploads once as multipart, is ready without a second API call, and shows only reported OCR values", async () => {
    let release: (reply: MockReply) => void = () => {};
    const { user, fetchMock } = await openPage({
      [`POST ${INGEST_IMAGE}`]: () => new Promise<MockReply>((resolve) => (release = resolve)),
    });
    await pick(user, image("Notice.png"));

    await user.click(submit());

    expect(await screen.findByText("Uploading, reading text with OCR and indexing…")).toBeInTheDocument();
    expect(submit()).toBeDisabled();
    expect(screen.queryByTestId("image-ready")).not.toBeInTheDocument();

    const [, init] = calls(fetchMock, "POST", INGEST_IMAGE)[0];
    const headers = init?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer test-access-token");
    expect(headers["Content-Type"]).toBeUndefined();
    expect(init?.body).toBeInstanceOf(FormData);
    expect((init?.body as FormData).get("file")).toMatchObject({ name: "Notice.png" });

    release(created(INGESTED));
    const ready = await screen.findByTestId("image-ready");
    expect(ready).toHaveTextContent("Ready to search");
    expect(ready).toHaveTextContent("Text was read from Notice.png (2 text passages; 4 lines read, 98% average OCR confidence)");
    expect(ready).toHaveTextContent("Only your account has been granted access to this image");
    expect(within(ready).getByRole("link", { name: "Ask the assistant" })).toHaveAttribute("href", "/app/chat");
    expect(calls(fetchMock, "POST", INGEST_IMAGE)).toHaveLength(1);
    expect(calls(fetchMock, "POST", EMBED)).toHaveLength(0);
    expect(calls(fetchMock, "POST", INGEST_PDF)).toHaveLength(0);
    expect(screen.queryByTestId("selected-file")).not.toBeInTheDocument();
  });

  it("omits OCR statistics the server did not report validly", async () => {
    const { user } = await openPage({
      [`POST ${INGEST_IMAGE}`]: created({ ...INGESTED, ocr_line_count: 0, ocr_mean_confidence: 1.7 }),
    });
    await pick(user);

    await user.click(submit());

    const ready = await screen.findByTestId("image-ready");
    expect(ready).toHaveTextContent("Text was read from Notice.png (2 text passages) and indexed.");
    expect(ready).not.toHaveTextContent("lines read");
    expect(ready).not.toHaveTextContent("confidence");
  });

  it("opens the assistant from the success state", async () => {
    const { user } = await openPage({ [`POST ${INGEST_IMAGE}`]: created(INGESTED) });
    await pick(user);
    await user.click(submit());

    await user.click(await screen.findByRole("link", { name: "Ask the assistant" }));

    expect(await screen.findByRole("heading", { level: 2, name: "Enterprise Assistant" })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/app/chat");
  });

  it.each([
    ["failed", "The server reported that indexing failed."],
    ["not_configured", "The server reported that the embedding service is not configured."],
    ["pending", "The server did not confirm that indexing completed."],
    [undefined, "The server did not confirm that indexing completed."],
  ])("is stored but not searchable when embedding_status is %s", async (embeddingStatus, reason) => {
    const { user } = await openPage({
      [`POST ${INGEST_IMAGE}`]: created({ ...INGESTED, embedding_status: embeddingStatus }),
    });
    await pick(user);

    await user.click(submit());

    const failed = await screen.findByTestId("image-index-failed");
    expect(failed).toHaveTextContent("Stored, but not searchable yet");
    expect(failed).toHaveTextContent(reason);
    expect(failed).toHaveTextContent("Retrying does not upload the image again.");
    expect(screen.queryByTestId("image-ready")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Ask the assistant" })).not.toBeInTheDocument();
  });

  it("retries indexing with the stored document id and never uploads the image again", async () => {
    let embedReply: MockReply = error(503, "The embedding provider is not configured.");
    const { user, fetchMock } = await openPage({
      [`POST ${INGEST_IMAGE}`]: created({ ...INGESTED, embedding_status: "not_configured" }),
      [`POST ${EMBED}`]: () => embedReply,
    });
    await pick(user);
    await user.click(submit());
    const failed = await screen.findByTestId("image-index-failed");

    await user.click(within(failed).getByRole("button", { name: "Retry indexing" }));
    const stillFailed = await screen.findByTestId("image-index-failed");
    expect(stillFailed).toHaveTextContent("The embedding service isn't configured on the server");
    expect(screen.queryByTestId("image-ready")).not.toBeInTheDocument();

    embedReply = { body: EMBEDDED };
    await user.click(within(stillFailed).getByRole("button", { name: "Retry indexing" }));

    const ready = await screen.findByTestId("image-ready");
    expect(ready).toHaveTextContent("Ready to search");
    expect(calls(fetchMock, "POST", INGEST_IMAGE)).toHaveLength(1);
    expect(calls(fetchMock, "POST", EMBED)).toHaveLength(2);
    expect((calls(fetchMock, "POST", EMBED)[0][1]?.headers as Record<string, string>).Authorization).toBe(
      "Bearer test-access-token",
    );
  });

  it("does not report success when a retry response does not confirm indexing", async () => {
    const { user } = await openPage({
      [`POST ${INGEST_IMAGE}`]: created({ ...INGESTED, embedding_status: "failed" }),
      [`POST ${EMBED}`]: { body: { ...EMBEDDED, embeddings_created: 0 } },
    });
    await pick(user);
    await user.click(submit());

    await user.click(within(await screen.findByTestId("image-index-failed")).getByRole("button", { name: "Retry indexing" }));

    await waitFor(() => expect(screen.getByTestId("image-index-failed")).toHaveTextContent("The server returned an unexpected response."));
    expect(screen.queryByTestId("image-ready")).not.toBeInTheDocument();
  });

  it("shows the server's own message for invalid, oversized and text-less images", async () => {
    let reply: MockReply = error(400, "The uploaded file is not a valid image.");
    const { user } = await openPage({ [`POST ${INGEST_IMAGE}`]: () => reply });
    await pick(user);

    await user.click(submit());
    expect(await screen.findByRole("alert")).toHaveTextContent("This image can't be uploaded. The uploaded file is not a valid image.");

    reply = error(413, "The image must be no larger than 10 MB.");
    await user.click(submit());
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Image too large"));
    expect(screen.getByRole("alert")).toHaveTextContent("The image must be no larger than 10 MB.");

    reply = error(422, "No readable text was found in the image.");
    await user.click(submit());
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("No readable text found"));
    expect(screen.getByRole("alert")).toHaveTextContent("No readable text was found in the image.");
    expect(screen.queryByTestId("image-ready")).not.toBeInTheDocument();
    // The image stays selected so it can be replaced or retried.
    expect(screen.getByTestId("selected-file")).toBeInTheDocument();
  });

  it("explains OCR failures, a missing OCR engine, permission denial and server errors with safe copy", async () => {
    let reply: MockReply = error(502, "The image could not be processed by OCR.");
    const { user } = await openPage({ [`POST ${INGEST_IMAGE}`]: () => reply });
    await pick(user);

    const expected: [MockReply, string][] = [
      [reply, "Text recognition failed"],
      [error(503, "OCR is not available on the server."), "OCR isn't available"],
      [error(403, "You do not have permission to perform this action."), "Upload not permitted"],
      [error(500, "Traceback: /srv/app/ocr.py line 9"), "Upload failed"],
    ];
    for (const [next, title] of expected) {
      reply = next;
      await user.click(submit());
      await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(title));
    }
    expect(document.body.textContent).not.toContain("Traceback");
  });

  it("reports an unreachable server and lets the person try again", async () => {
    let reachable = false;
    const { user } = await openPage({
      [`POST ${INGEST_IMAGE}`]: () => {
        if (!reachable) throw new TypeError("Failed to fetch");
        return created(INGESTED);
      },
    });
    await pick(user);

    await user.click(submit());
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach Nexora");
    expect(submit()).toBeEnabled();

    reachable = true;
    await user.click(submit());
    expect(await screen.findByTestId("image-ready")).toBeInTheDocument();
  });

  it("treats an unexpected or incomplete response as a failure, never as success", async () => {
    const { user } = await openPage({
      [`POST ${INGEST_IMAGE}`]: created({ filename: "Notice.png", status: "processed", embedding_status: "completed" }),
    });
    await pick(user);

    await user.click(submit());

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.queryByTestId("image-ready")).not.toBeInTheDocument();
  });

  it("rejects a response that is not for an image document", async () => {
    const { user } = await openPage({ [`POST ${INGEST_IMAGE}`]: created({ ...INGESTED, source_type: "pdf" }) });
    await pick(user);

    await user.click(submit());

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.queryByTestId("image-ready")).not.toBeInTheDocument();
  });

  it("returns to the login page when the session expires during upload", async () => {
    const { user } = await openPage({ [`POST ${INGEST_IMAGE}`]: error(401, "expired") });
    await pick(user);

    await user.click(submit());

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/login"));
    expect(getAccessToken()).toBeNull();
  });
});
