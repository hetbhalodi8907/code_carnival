import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { DocumentChat } from "@/components/documents/DocumentChat";
import { calls, mockFetch, renderApp, signIn, FINANCE_MANAGER, type MockReply } from "@/test/utils";
import type { AssistantQueryResponse, CurrentUser, DocumentIngestionResponse, ImageIngestionResponse } from "@/types/api";

const ADMIN: CurrentUser = {
  ...FINANCE_MANAGER,
  email: "ishaan.malhotra@nexora.example",
  full_name: "Ishaan Malhotra",
  roles: ["SUPER_ADMIN"],
  permissions: ["documents:read", "documents:write"],
};
const ME = { "GET /api/v1/auth/me": { body: ADMIN } };
const ASK = "/api/v1/assistant/document-query";
const MAIN_ASSISTANT = "/api/v1/assistant/query";
const PDF_ID = "5f6c1c0e-0000-4000-8000-00000000abcd";
const IMG_ID = "5f6c1c0e-0000-4000-8000-00000000beef";
const MODEL = "sentence-transformers/all-MiniLM-L6-v2";

const PDF_INGESTED: DocumentIngestionResponse = {
  document_id: PDF_ID, filename: "Budget.pdf", source_type: "pdf", source_path: `${PDF_ID}.pdf`, page_count: 3, chunk_count: 6,
  status: "processed", embedding_status: "completed", embedding_model: MODEL,
};
const IMG_INGESTED: ImageIngestionResponse = {
  document_id: IMG_ID, filename: "notice.png", source_type: "image", source_path: `${IMG_ID}.png`, chunk_count: 1, ocr_line_count: 4,
  ocr_mean_confidence: 0.93, embedding_status: "completed", status: "processed",
} as ImageIngestionResponse;

const pdfSource = { source_number: 1, document_id: PDF_ID, document_title: "Budget.pdf", chunk_id: "c-pdf-1", page_number: 2, source_locator: "page:2", similarity: 0.81, source_type: "pdf" };
const imageSource = { source_number: 1, document_id: IMG_ID, document_title: "notice.png", chunk_id: "c-img-1", page_number: null, source_locator: "image:ocr", similarity: 0.7, source_type: "image" };
const TRUST = { authorization: "access_controlled_retrieval" as const, authorized_source_count: 1, provider: "groq", model: "openai/gpt-oss-120b" };

function answered(answer: string, source: Record<string, unknown> = pdfSource): MockReply {
  const body: AssistantQueryResponse = {
    status: "answered", answer, request_id: "r", sources: [source as never], unverified_source_numbers: [1], rejected_source_numbers: [],
    citation_check: "passed", trust_proof: TRUST,
  } as AssistantQueryResponse;
  return { body };
}
const insufficient: MockReply = {
  body: { status: "insufficient_context", answer: "The documents you're authorized to access don't contain enough information to answer this question.", request_id: "r", sources: [], unverified_source_numbers: [], rejected_source_numbers: [], citation_check: "not_applicable", trust_proof: null },
};
const failure = (status: number, message = "server detail"): MockReply => ({ status, body: { error: { code: "HTTP_ERROR", message, request_id: "r" } } });

function file(name: string, type: string) {
  const f = new File(["bytes"], name, { type });
  Object.defineProperty(f, "size", { value: 2048 });
  return f;
}
const sent = (fetchMock: ReturnType<typeof mockFetch>, index = 0) => JSON.parse(String(calls(fetchMock, "POST", ASK)[index][1]?.body));

async function uploadPdf(routes: Record<string, unknown>) {
  signIn();
  const fetchMock = mockFetch({ ...ME, "POST /api/v1/documents/ingest": { status: 201, body: PDF_INGESTED }, ...routes } as never);
  const user = userEvent.setup({ applyAccept: false });
  renderApp("/app/upload");
  await user.upload(await screen.findByLabelText(/choose a file/i), file("Budget.pdf", "application/pdf"));
  await user.click(screen.getByRole("button", { name: "Upload and index" }));
  await screen.findByTestId("upload-ready");
  return { user, fetchMock };
}

async function ask(user: ReturnType<typeof userEvent.setup>, question: string) {
  await user.type(screen.getByLabelText("Ask about this document"), question);
  await user.click(screen.getByRole("button", { name: "Send document question" }));
}

describe("document chat on the PDF upload page", () => {
  it("appears only after indexing is confirmed, with the document named", async () => {
    signIn();
    mockFetch({ ...ME, "POST /api/v1/documents/ingest": { status: 201, body: PDF_INGESTED } } as never);
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload");
    await screen.findByLabelText(/choose a file/i);
    expect(screen.queryByTestId("document-chat")).not.toBeInTheDocument(); // nothing before an upload
    await user.upload(screen.getByLabelText(/choose a file/i), file("Budget.pdf", "application/pdf"));
    await user.click(screen.getByRole("button", { name: "Upload and index" }));

    const chat = await screen.findByTestId("document-chat");
    expect(within(chat).getByRole("heading", { name: "Chat with this document" })).toBeInTheDocument();
    expect(chat).toHaveTextContent("Budget.pdf");
    expect(within(chat).getByText("Indexed")).toBeInTheDocument();
    expect(within(chat).getByTestId("document-chat-welcome")).toHaveTextContent("answering only from Budget.pdf");
    expect(within(chat).getByRole("button", { name: "New conversation" })).toBeDisabled();
  });

  it("is not offered when indexing failed, was not configured or is unconfirmed", async () => {
    for (const embedding_status of ["failed", "not_configured", null]) {
      signIn();
      mockFetch({ ...ME, "POST /api/v1/documents/ingest": { status: 201, body: { ...PDF_INGESTED, embedding_status, embedding_model: null } } } as never);
      const user = userEvent.setup({ applyAccept: false });
      renderApp("/app/upload");
      await user.upload(await screen.findByLabelText(/choose a file/i), file("Budget.pdf", "application/pdf"));
      await user.click(screen.getByRole("button", { name: "Upload and index" }));
      expect(await screen.findByTestId("upload-index-failed")).toHaveTextContent("Stored, but not searchable yet");
      expect(screen.queryByTestId("document-chat")).not.toBeInTheDocument();
      cleanup();
    }
  });

  it("asks the document-scoped endpoint with the selected document and shows the answer, page source and receipt", async () => {
    const { user, fetchMock } = await uploadPdf({ [`POST ${ASK}`]: answered("The total budget is INR 2.4 crore [S1].") });
    await ask(user, "What is the total budget?");

    const reply = await screen.findByText(/INR 2.4 crore/);
    expect(reply).toBeInTheDocument();
    expect(sent(fetchMock)).toEqual({ document_id: PDF_ID, query: "What is the total budget?", history: [] });
    expect(calls(fetchMock, "POST", MAIN_ASSISTANT)).toHaveLength(0); // never the all-documents assistant
    const sources = screen.getByRole("region", { name: "Sources retrieved for this answer" });
    expect(sources).toHaveTextContent("Budget.pdf");
    expect(sources).toHaveTextContent("p. 2");
    expect(screen.getByTestId("trustproof")).toBeInTheDocument();
    expect(calls(fetchMock, "POST", ASK)).toHaveLength(1);
    expect((calls(fetchMock, "POST", ASK)[0][1]?.headers as Record<string, string>).Authorization).toBe("Bearer test-access-token");
  });

  it("sends earlier turns with each follow-up and stays on the same document", async () => {
    let n = 0;
    const { user, fetchMock } = await uploadPdf({
      [`POST ${ASK}`]: () => (++n === 1 ? answered("The total budget is INR 2.4 crore [S1].") : answered("In simple terms: about two and a half crore rupees [S1].")),
    });
    await ask(user, "What is the total budget?");
    await screen.findByText(/INR 2.4 crore/);
    await ask(user, "Explain that in simpler words");
    await screen.findByText(/two and a half crore/);

    expect(sent(fetchMock, 1)).toEqual({
      document_id: PDF_ID,
      query: "Explain that in simpler words",
      history: [
        { role: "user", content: "What is the total budget?" },
        { role: "assistant", content: "The total budget is INR 2.4 crore [S1]." },
      ],
    });
    expect(calls(fetchMock, "POST", MAIN_ASSISTANT)).toHaveLength(0);
    expect(screen.getAllByTestId("trustproof")).toHaveLength(2); // two answers, one conversation
  });

  it("caps the history it sends at 10 turns", async () => {
    const { user, fetchMock } = await uploadPdf({ [`POST ${ASK}`]: answered("Answer [S1].") });
    for (let i = 1; i <= 7; i++) {
      await ask(user, `Question number ${i}`);
      await waitFor(() => expect(calls(fetchMock, "POST", ASK)).toHaveLength(i));
      await waitFor(() => expect(screen.getByRole("button", { name: "Send document question" })).toBeDisabled()); // draft empty again
      await waitFor(() => expect(screen.getAllByTestId("trustproof")).toHaveLength(i));
    }
    expect(sent(fetchMock, 6).history).toHaveLength(10);
    expect(sent(fetchMock, 6).history[0]).toEqual({ role: "user", content: "Question number 2" });
  });

  it("keeps insufficient-information semantics: the established message, no sources, never Access Denied", async () => {
    const { user } = await uploadPdf({ [`POST ${ASK}`]: insufficient });
    await ask(user, "What is the capital of France?");

    expect(await screen.findByTestId("insufficient-context")).toBeInTheDocument();
    expect(screen.queryByTestId("access-denied")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Sources retrieved for this answer" })).not.toBeInTheDocument();
  });

  it("shows a rate limit as a retryable error, keeps the question, and retries once per click", async () => {
    let n = 0;
    const { user, fetchMock } = await uploadPdf({ [`POST ${ASK}`]: () => (++n === 1 ? failure(429, "quota detail") : answered("Recovered [S1].")) });
    await ask(user, "What is the total budget?");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The assistant is busy");
    expect(document.body.textContent).not.toContain("quota detail");
    expect(screen.getByText("What is the total budget?")).toBeInTheDocument(); // the question stays on screen
    expect(screen.queryByTestId("access-denied")).not.toBeInTheDocument();
    expect(screen.queryByTestId("trustproof")).not.toBeInTheDocument(); // a failed request is never a receipt
    expect(calls(fetchMock, "POST", ASK)).toHaveLength(1); // no automatic repeat

    await user.click(within(alert).getByRole("button", { name: /try again|retry/i }));
    expect(await screen.findByText(/Recovered/)).toBeInTheDocument();
    expect(calls(fetchMock, "POST", ASK)).toHaveLength(2);
    expect(sent(fetchMock, 1)).toEqual(sent(fetchMock, 0));
  });

  it("explains a document that is no longer available without revealing anything", async () => {
    const { user } = await uploadPdf({ [`POST ${ASK}`]: failure(404, "The document was not found.") });
    await ask(user, "What is the total budget?");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Document not available");
    expect(within(alert).queryByRole("button", { name: /try again|retry/i })).not.toBeInTheDocument();
  });

  it("starts over on New conversation: the history is gone and the next question carries none", async () => {
    const { user, fetchMock } = await uploadPdf({ [`POST ${ASK}`]: answered("The total budget is INR 2.4 crore [S1].") });
    await ask(user, "What is the total budget?");
    await screen.findByText(/INR 2.4 crore/);

    await user.click(screen.getByRole("button", { name: "New conversation" }));
    expect(screen.queryByText(/INR 2.4 crore/)).not.toBeInTheDocument();
    expect(screen.queryByText("What is the total budget?")).not.toBeInTheDocument();
    expect(screen.getByTestId("document-chat-welcome")).toBeInTheDocument();

    await ask(user, "Which project is largest?");
    await screen.findByText(/INR 2.4 crore/);
    expect(sent(fetchMock, 1).history).toEqual([]); // nothing from the cleared conversation
  });

  it("removes the chat with 'Upload another' and starts a fresh conversation for the next document", async () => {
    const OTHER_ID = "5f6c1c0e-0000-4000-8000-00000000cafe";
    let uploads = 0;
    const { user, fetchMock } = await uploadPdf({
      "POST /api/v1/documents/ingest": () => ({ status: 201, body: ++uploads === 1 ? PDF_INGESTED : { ...PDF_INGESTED, document_id: OTHER_ID, filename: "Second.pdf" } }),
      [`POST ${ASK}`]: answered("The total budget is INR 2.4 crore [S1]."),
    });
    await ask(user, "What is the total budget?");
    await screen.findByText(/INR 2.4 crore/);

    await user.click(screen.getByRole("button", { name: "Upload another" }));
    expect(screen.queryByTestId("document-chat")).not.toBeInTheDocument();

    await user.upload(screen.getByLabelText(/choose a file/i), file("Second.pdf", "application/pdf"));
    await user.click(screen.getByRole("button", { name: "Upload and index" }));
    const chat = await screen.findByTestId("document-chat");
    expect(chat).toHaveTextContent("Second.pdf");
    expect(screen.queryByText(/INR 2.4 crore/)).not.toBeInTheDocument(); // the first document's conversation is gone
    await ask(user, "And here?");
    await screen.findByText(/INR 2.4 crore/);
    expect(sent(fetchMock, 1)).toEqual({ document_id: OTHER_ID, query: "And here?", history: [] });
  });
});

describe("document chat component", () => {
  it("drops the conversation when it is given a different document", async () => {
    signIn();
    mockFetch({ ...ME, [`POST ${ASK}`]: answered("First document answer [S1].") } as never);
    const user = userEvent.setup();
    const view = render(<DocumentChat documentId={PDF_ID} filename="A.pdf" kind="pdf" />);
    await ask(user, "What is in it?");
    await screen.findByText(/First document answer/);

    view.rerender(<DocumentChat documentId={IMG_ID} filename="B.png" kind="image" />);
    expect(screen.queryByText(/First document answer/)).not.toBeInTheDocument();
    expect(screen.getByTestId("document-chat-welcome")).toHaveTextContent("B.png");
  });
});

describe("document chat on the image (OCR) upload page", () => {
  it("is enabled by a successful OCR upload and cites OCR text without inventing a page", async () => {
    signIn();
    const fetchMock = mockFetch({ ...ME, "POST /api/v1/documents/ingest-image": { status: 201, body: IMG_INGESTED }, [`POST ${ASK}`]: answered("The cafeteria closes on Friday [S1].", imageSource) } as never);
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload-image");
    await user.upload(await screen.findByLabelText(/choose a file/i), file("notice.png", "image/png"));
    await user.click(screen.getByRole("button", { name: "Upload and read" }));

    const chat = await screen.findByTestId("document-chat");
    expect(chat).toHaveTextContent("notice.png");
    expect(within(chat).getByTestId("document-chat-welcome")).toHaveTextContent("this image");
    await user.type(screen.getByLabelText("Ask about this document"), "When does the cafeteria close?");
    await user.click(screen.getByRole("button", { name: "Send document question" }));

    await screen.findByText(/cafeteria closes/);
    expect(sent(fetchMock)).toEqual({ document_id: IMG_ID, query: "When does the cafeteria close?", history: [] });
    const sources = screen.getByRole("region", { name: "Sources retrieved for this answer" });
    expect(sources).toHaveTextContent("notice.png");
    expect(sources).toHaveTextContent("OCR text");
    expect(sources).not.toHaveTextContent(/p\. \d/); // an image has no page
    expect(calls(fetchMock, "POST", "/api/v1/documents/ingest-image")).toHaveLength(1); // OCR ran once, at upload
  });

  it("is not offered when indexing did not complete", async () => {
    signIn();
    mockFetch({ ...ME, "POST /api/v1/documents/ingest-image": { status: 201, body: { ...IMG_INGESTED, embedding_status: "failed" } } } as never);
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/app/upload-image");
    await user.upload(await screen.findByLabelText(/choose a file/i), file("notice.png", "image/png"));
    await user.click(screen.getByRole("button", { name: "Upload and read" }));
    expect(await screen.findByTestId("image-index-failed")).toHaveTextContent("Stored, but not searchable yet");
    expect(screen.queryByTestId("document-chat")).not.toBeInTheDocument();
  });
});
