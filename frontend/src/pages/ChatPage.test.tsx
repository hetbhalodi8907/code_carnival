import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { getAccessToken } from "@/services/session";
import type { AssistantQueryResponse, VectorSearchResponse } from "@/types/api";
import { FINANCE_MANAGER, NOT_FOUND, calls, mockFetch, renderApp, signIn, type MockReply } from "@/test/utils";

const ME = { "GET /api/v1/auth/me": { body: FINANCE_MANAGER } };

const ANSWERED: AssistantQueryResponse = {
  status: "answered",
  answer: "The Finance Department Annual Budget for FY 2025-26 is INR 1.5 crore.",
  citations: [
    {
      document_id: "d1",
      document_title: "Finance_Report.pdf",
      page_number: 2,
      chunk_id: "c1",
      similarity: 0.91,
      excerpt: "Finance Department Annual Budget: INR 1.5 crore.",
    },
  ],
};

const SEARCH: VectorSearchResponse = {
  query: "q",
  top_k: 5,
  distance_metric: "cosine",
  embedding_model: "text-embedding-3-small",
  results: [
    {
      chunk_id: "c9",
      document_id: "d9",
      chunk_index: 1,
      page_number: 2,
      source_locator: "page:2",
      content: "Finance Department Annual Budget: INR 1.5 crore.",
      distance: 0.18,
      similarity: 0.82,
    },
  ],
};

async function ask(question: string) {
  const user = userEvent.setup();
  const input = await screen.findByLabelText("Ask a question");
  await user.clear(input);
  await user.type(input, question);
  await user.click(screen.getByRole("button", { name: "Send question" }));
  return user;
}

describe("chat", () => {
  it("shows the signed-in role and fills (but does not send) example prompts", async () => {
    signIn();
    const fetchMock = mockFetch(ME);
    const user = userEvent.setup();
    renderApp("/app/chat");

    expect(await screen.findByTestId("current-user-role")).toHaveTextContent("Finance Manager");
    await user.click(screen.getByRole("button", { name: /What is the MFA policy\?/ }));

    expect(screen.getByLabelText("Ask a question")).toHaveValue("What is the MFA policy?");
    await user.click(screen.getByRole("button", { name: "HR Policy" }));
    expect(screen.getByLabelText("Ask a question")).toHaveValue("What is the HR performance review cycle?");
    expect(calls(fetchMock, "POST", "/api/v1/assistant/query")).toHaveLength(0);
  });

  it("submits the question, shows the loading state, then the answer with citations", async () => {
    signIn();
    let release: (reply: MockReply) => void = () => {};
    const fetchMock = mockFetch({
      ...ME,
      "POST /api/v1/assistant/query": () => new Promise<MockReply>((resolve) => (release = resolve)),
    });
    renderApp("/app/chat");

    const user = await ask("What is the Finance department budget?");

    expect(await screen.findByText("Retrieving authorized sources…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send question" })).toBeDisabled();
    release({ body: ANSWERED });

    expect(await screen.findByText(ANSWERED.answer!)).toBeInTheDocument();
    const chip = screen.getByRole("button", { name: /Finance_Report\.pdf/ });
    expect(chip).toHaveTextContent("p. 2");
    await user.click(chip);
    expect(screen.getByTestId("source-card")).toHaveTextContent("Similarity 91%");
    expect(screen.getByTestId("source-card")).toHaveTextContent("Page 2");
    const body = JSON.parse(String(calls(fetchMock, "POST", "/api/v1/assistant/query")[0][1]?.body));
    expect(body).toEqual({ question: "What is the Finance department budget?" });
  });

  it("renders the safe access-restricted state without naming any source", async () => {
    signIn();
    mockFetch({
      ...ME,
      "POST /api/v1/assistant/query": { body: { status: "no_authorized_context", answer: null, citations: [] } },
    });
    renderApp("/app/chat");

    await ask("What is the confidential HR policy?");

    const restricted = await screen.findByTestId("access-restricted");
    expect(restricted).toHaveTextContent("Access restricted");
    expect(restricted).toHaveTextContent("I don’t have access to information required to answer this question.");
    expect(screen.queryByRole("region", { name: "Sources" })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/HR_Policy|\.pdf/);
  });

  it("falls back to authorized vector search while the assistant endpoint does not exist", async () => {
    signIn();
    const fetchMock = mockFetch({
      ...ME,
      "POST /api/v1/assistant/query": NOT_FOUND,
      "POST /api/v1/search/vector": { body: SEARCH },
    });
    renderApp("/app/chat");

    await ask("What is the Finance department budget?");

    expect(await screen.findByText(/most relevant passages from sources you’re authorized to access/)).toBeInTheDocument();
    const card = screen.getByTestId("source-card");
    expect(card).toHaveTextContent("Authorized source");
    expect(card).toHaveTextContent("Similarity 82%");
    expect(JSON.parse(String(calls(fetchMock, "POST", "/api/v1/search/vector")[0][1]?.body))).toEqual({
      query: "What is the Finance department budget?",
      top_k: 5,
    });

    await ask("And the engineering allocation?");
    await waitFor(() => expect(calls(fetchMock, "POST", "/api/v1/search/vector")).toHaveLength(2));
    expect(calls(fetchMock, "POST", "/api/v1/assistant/query")).toHaveLength(1);
  });

  it("treats a server-side 403 as restricted and 503 as a temporary outage", async () => {
    signIn();
    let status = 403;
    mockFetch({
      ...ME,
      "POST /api/v1/assistant/query": () => ({
        status,
        body: { error: { code: "HTTP_ERROR", message: "internal detail", request_id: "r" } },
      }),
    });
    renderApp("/app/chat");

    await ask("Show me everything");
    expect(await screen.findByTestId("access-restricted")).toBeInTheDocument();

    status = 503;
    await ask("Try again");
    expect(await screen.findByText("Service temporarily unavailable")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("internal detail");
  });

  it("returns to the login page with a notice when the session expires mid-chat", async () => {
    signIn();
    mockFetch({
      ...ME,
      "POST /api/v1/assistant/query": { status: 401, body: { error: { code: "HTTP_ERROR", message: "x" } } },
    });
    renderApp("/app/chat");

    await ask("What is the Finance department budget?");

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/login"));
    expect(screen.getByRole("status")).toHaveTextContent("Your session has expired. Please sign in again.");
    expect(getAccessToken()).toBeNull();
  });
});
