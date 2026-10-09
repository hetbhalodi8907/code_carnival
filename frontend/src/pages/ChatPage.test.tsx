import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { getAccessToken } from "@/services/session";
import type { AssistantQueryResponse } from "@/types/api";
import { FINANCE_MANAGER, NOT_FOUND, calls, mockFetch, renderApp, signIn, type MockReply } from "@/test/utils";

const ME = { "GET /api/v1/auth/me": { body: FINANCE_MANAGER } };
const PATH = "/api/v1/assistant/query";
const QUESTION = "What is the Finance department budget?";

const ANSWERED: AssistantQueryResponse = {
  status: "answered",
  answer: "The Finance department budget for FY 2025-26 is INR 1.5 crore [S1].",
  request_id: "req-1",
  sources: [
    {
      source_number: 1,
      document_id: "d1",
      document_title: "Nexora Finance Report FY 2025-26",
      chunk_id: "c1",
      page_number: 2,
      source_locator: "page:2",
      similarity: 0.8246,
    },
    {
      source_number: 2,
      document_id: "d2",
      document_title: "Nexora Procurement Report FY 2025-26",
      chunk_id: "c2",
      page_number: null,
      source_locator: null,
      similarity: 0.61,
    },
  ],
  unverified_source_numbers: [1, 7],
};

const NO_CONTEXT_MESSAGE = "I couldn't find any information you're authorized to access that answers this question.";
const INSUFFICIENT_MESSAGE =
  "The documents you're authorized to access don't contain enough information to answer this question.";

function fixedReply(status: AssistantQueryResponse["status"], answer: string): MockReply {
  return { body: { status, answer, request_id: "r", sources: [], unverified_source_numbers: [] } };
}

function errorReply(status: number): MockReply {
  return { status, body: { error: { code: "HTTP_ERROR", message: "internal detail: provider stack", request_id: "r" } } };
}

async function ask(question: string) {
  const user = userEvent.setup();
  const input = await screen.findByLabelText("Ask a question");
  await user.clear(input);
  await user.type(input, question);
  await user.click(screen.getByRole("button", { name: "Send question" }));
  return user;
}

/** The innermost element whose whole text is `text` (wrappers with the same text are skipped). */
function exactText(text: string) {
  return (_: string, element: Element | null) =>
    element?.textContent === text && Array.from(element.children).every((child) => child.textContent !== text);
}

function userMessages(question: string) {
  return screen.queryAllByText(exactText(`You asked: ${question}`));
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
    await user.click(screen.getByRole("button", { name: /What is the HR performance review cycle\?/ }));
    expect(screen.getByLabelText("Ask a question")).toHaveValue("What is the HR performance review cycle?");
    expect(calls(fetchMock, "POST", PATH)).toHaveLength(0);
  });

  it("sends the query, shows the loading state, then the answer with its retrieved sources", async () => {
    signIn();
    let release: (reply: MockReply) => void = () => {};
    const fetchMock = mockFetch({ ...ME, [`POST ${PATH}`]: () => new Promise<MockReply>((resolve) => (release = resolve)) });
    renderApp("/app/chat");

    const user = await ask(QUESTION);

    expect(await screen.findByText("Retrieving authorized sources…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send question" })).toBeDisabled();
    expect(JSON.parse(String(calls(fetchMock, "POST", PATH)[0][1]?.body))).toEqual({ query: QUESTION, top_k: 5 });
    release({ body: ANSWERED });

    expect(await screen.findByText(ANSWERED.answer)).toBeInTheDocument();
    expect(screen.getAllByText(ANSWERED.answer)).toHaveLength(1);
    expect(screen.queryByText("Retrieving authorized sources…")).not.toBeInTheDocument();

    const sources = screen.getByRole("region", { name: "Sources retrieved for this answer" });
    expect(sources).toHaveTextContent("not yet verified as support for each statement");
    const chip = within(sources).getByRole("button", { name: /Nexora Finance Report FY 2025-26/ });
    expect(chip).toHaveTextContent("p. 2");
    // A null page renders no page label at all.
    expect(within(sources).getByRole("button", { name: /Nexora Procurement Report/ })).not.toHaveTextContent("p.");
    await user.click(chip);
    const card = screen.getByTestId("source-card");
    expect(card).toHaveTextContent("Page 2");
    expect(card).toHaveTextContent("Similarity 0.82");
    expect(card).not.toHaveTextContent("%");

    // Model references stay explicitly unverified and are not linked to any source.
    expect(screen.getByTestId("unverified-references")).toHaveTextContent(
      "References [S1], [S7] in this answer were suggested by the AI and have not been verified",
    );
    expect(screen.queryByText(/S1.*Finance Report/)).not.toBeInTheDocument();
  });

  it("shows the server's message when the authorized sources do not answer the question", async () => {
    signIn();
    mockFetch({ ...ME, [`POST ${PATH}`]: fixedReply("insufficient_context", INSUFFICIENT_MESSAGE) });
    renderApp("/app/chat");

    await ask("What is the parental leave policy?");

    const notice = await screen.findByTestId("insufficient-context");
    expect(notice).toHaveTextContent("Not enough information");
    expect(notice).toHaveTextContent(INSUFFICIENT_MESSAGE);
    expect(screen.queryByRole("region", { name: "Sources retrieved for this answer" })).not.toBeInTheDocument();
  });

  it("shows the server's safe message when no authorized source exists, naming no document", async () => {
    signIn();
    mockFetch({ ...ME, [`POST ${PATH}`]: fixedReply("no_authorized_context", NO_CONTEXT_MESSAGE) });
    renderApp("/app/chat");

    await ask("What is the confidential HR policy?");

    const notice = await screen.findByTestId("no-authorized-context");
    expect(notice).toHaveTextContent("No authorized information found");
    expect(notice).toHaveTextContent(NO_CONTEXT_MESSAGE);
    expect(screen.queryByRole("region", { name: "Sources retrieved for this answer" })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/HR_Policy|Human Resources Policy|\.pdf/);
  });

  it("shows safe errors for each failure status, never as answers and never via plain search", async () => {
    signIn();
    let status = 403;
    const fetchMock = mockFetch({ ...ME, [`POST ${PATH}`]: () => errorReply(status), "POST /api/v1/search/vector": { body: {} } });
    renderApp("/app/chat");

    const expected: [number, string, boolean][] = [
      [403, "Access restricted", false],
      [422, "Question not accepted", false],
      [500, "Something went wrong", true],
      [502, "The assistant couldn't answer", true],
      [503, "Service temporarily unavailable", true],
      [504, "The assistant timed out", true],
      [404, "Not available", false],
    ];
    for (const [code, title, retryable] of expected) {
      status = code;
      await ask(`Question for ${code}`);
      const alerts = await screen.findAllByRole("alert");
      const alert = alerts[alerts.length - 1];
      await waitFor(() => expect(alert).toHaveTextContent(title));
      expect(within(alert).queryByRole("button", { name: "Retry" }) !== null).toBe(retryable);
    }
    expect(document.body.textContent).not.toContain("internal detail");
    expect(calls(fetchMock, "POST", "/api/v1/search/vector")).toHaveLength(0);
    expect(screen.queryByText("Retrieving authorized sources…")).not.toBeInTheDocument();
  });

  it("retries a failed question in place without duplicating messages", async () => {
    signIn();
    let reply: MockReply = errorReply(503);
    const fetchMock = mockFetch({ ...ME, [`POST ${PATH}`]: () => reply });
    renderApp("/app/chat");

    const user = await ask(QUESTION);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Service temporarily unavailable");

    reply = { body: ANSWERED };
    await user.click(within(alert).getByRole("button", { name: "Retry" }));

    expect(await screen.findByText(ANSWERED.answer)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(userMessages(QUESTION)).toHaveLength(1);
    expect(screen.getAllByRole("article", { name: "Nexora AI response" })).toHaveLength(1);
    const requests = calls(fetchMock, "POST", PATH);
    expect(requests).toHaveLength(2);
    expect(requests.map(([, init]) => JSON.parse(String(init?.body)).query)).toEqual([QUESTION, QUESTION]);
  });

  it("allows only one request at a time and keeps replies with their questions", async () => {
    signIn();
    let release: (reply: MockReply) => void = () => {};
    const fetchMock = mockFetch({ ...ME, [`POST ${PATH}`]: () => new Promise<MockReply>((resolve) => (release = resolve)) });
    renderApp("/app/chat");

    const user = await ask("First question?");
    await screen.findByText("Retrieving authorized sources…");
    await user.type(screen.getByLabelText("Ask a question"), "Second question?{Enter}");
    expect(calls(fetchMock, "POST", PATH)).toHaveLength(1);

    release({ body: { ...ANSWERED, answer: "First answer [S1]." } });
    await screen.findByText("First answer [S1].");
    await user.click(screen.getByRole("button", { name: "Send question" }));
    await waitFor(() => expect(calls(fetchMock, "POST", PATH)).toHaveLength(2));
    release({ body: { ...ANSWERED, answer: "Second answer [S1]." } });
    await screen.findByText("Second answer [S1].");

    const order = [
      userMessages("First question?"),
      screen.getAllByText(exactText("First answer [S1].")),
      userMessages("Second question?"),
      screen.getAllByText(exactText("Second answer [S1].")),
    ].map((found) => {
      expect(found).toHaveLength(1); // each message and reply appears exactly once
      return found[0];
    });
    for (let index = 1; index < order.length; index += 1) {
      expect(order[index - 1].compareDocumentPosition(order[index]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it("treats network failures and unexpected bodies as errors, not answers", async () => {
    signIn();
    let reply: MockReply | "network" = "network";
    const fetchMock = mockFetch({
      ...ME,
      [`POST ${PATH}`]: () => {
        if (reply === "network") throw new TypeError("Failed to fetch");
        return reply;
      },
    });
    renderApp("/app/chat");

    await ask(QUESTION);
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach Nexora");

    reply = { body: { answer: "Looks like an answer", citations: [] } };
    await ask("Another question?");
    await waitFor(() => expect(screen.getAllByRole("alert")).toHaveLength(2));
    expect(screen.getAllByRole("alert")[1]).toHaveTextContent("Something went wrong");
    expect(screen.queryByText("Looks like an answer")).not.toBeInTheDocument();
    expect(calls(fetchMock, "POST", "/api/v1/search/vector")).toHaveLength(0);
  });

  it("does not fall back to plain search when the assistant route is missing", async () => {
    signIn();
    const fetchMock = mockFetch({ ...ME, [`POST ${PATH}`]: NOT_FOUND, "POST /api/v1/search/vector": { body: {} } });
    renderApp("/app/chat");

    await ask(QUESTION);

    expect(await screen.findByRole("alert")).toHaveTextContent("Not available");
    expect(calls(fetchMock, "POST", "/api/v1/search/vector")).toHaveLength(0);
  });

  it("returns to the login page with a notice when the session expires mid-chat", async () => {
    signIn();
    mockFetch({ ...ME, [`POST ${PATH}`]: { status: 401, body: { error: { code: "HTTP_ERROR", message: "x" } } } });
    renderApp("/app/chat");

    await ask(QUESTION);

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/login"));
    expect(screen.getByRole("status")).toHaveTextContent("Your session has expired. Please sign in again.");
    expect(getAccessToken()).toBeNull();
  });
});
