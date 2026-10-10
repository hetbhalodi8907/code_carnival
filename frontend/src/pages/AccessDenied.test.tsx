import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { AssistantQueryResponse } from "@/types/api";
import { FINANCE_MANAGER, calls, mockFetch, renderApp, signIn, type MockReply } from "@/test/utils";

const PATH = "/api/v1/assistant/query";
const ME = { "GET /api/v1/auth/me": { body: FINANCE_MANAGER } };

const DENIED_ANSWER = "You don't have permission to access the information requested.";
const INSUFFICIENT_ANSWER =
  "The documents you're authorized to access don't contain enough information to answer this question.";

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
  ],
  unverified_source_numbers: [1],
};

function reply(status: AssistantQueryResponse["status"], answer: string, extra: object = {}): MockReply {
  return {
    body: {
      status,
      answer,
      request_id: "r",
      sources: [],
      unverified_source_numbers: [],
      rejected_source_numbers: [],
      citation_check: "not_applicable",
      ...extra,
    },
  };
}

async function ask(question: string) {
  const user = userEvent.setup();
  const input = await screen.findByLabelText("Ask a question");
  await user.clear(input);
  await user.type(input, question);
  await user.click(screen.getByRole("button", { name: "Send question" }));
  return user;
}

describe("access denied state", () => {
  it("shows Access Denied with fixed copy, guidance and no sources when the server denies access", async () => {
    signIn();
    mockFetch({ ...ME, [`POST ${PATH}`]: reply("access_denied", DENIED_ANSWER) });
    renderApp("/app/chat");

    await ask("What are the confidential HR salary bands?");

    const denied = await screen.findByTestId("access-denied");
    expect(within(denied).getByRole("heading", { name: "Access Denied" })).toBeInTheDocument();
    expect(denied).toHaveTextContent(DENIED_ANSWER);
    expect(denied).toHaveTextContent("Contact your administrator if you believe you should have access.");
    expect(screen.queryByRole("region", { name: "Sources retrieved for this answer" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("insufficient-context")).not.toBeInTheDocument();
    expect(screen.queryByTestId("no-authorized-context")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders the denial from fixed copy, not from text the server sent with it", async () => {
    signIn();
    mockFetch({ ...ME, [`POST ${PATH}`]: reply("access_denied", "Denied: HR_Policy.pdf, page 7") });
    renderApp("/app/chat");

    await ask("What are the confidential HR salary bands?");

    const denied = await screen.findByTestId("access-denied");
    expect(denied).toHaveTextContent(DENIED_ANSWER);
    expect(document.body.textContent).not.toContain("HR_Policy");
  });

  it("refuses a malformed denial that carries sources, showing none of it", async () => {
    signIn();
    mockFetch({
      ...ME,
      [`POST ${PATH}`]: reply("access_denied", DENIED_ANSWER, {
        sources: ANSWERED.sources.map((source) => ({ ...source, document_title: "HR_Policy.pdf" })),
        unverified_source_numbers: [1],
      }),
    });
    renderApp("/app/chat");

    await ask("What are the confidential HR salary bands?");

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.queryByTestId("access-denied")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("HR_Policy");
  });

  it("keeps the insufficient-information response for an unanswered question, never a denial", async () => {
    signIn();
    mockFetch({ ...ME, [`POST ${PATH}`]: reply("insufficient_context", INSUFFICIENT_ANSWER) });
    renderApp("/app/chat");

    await ask("What is the capital of France?");

    const notice = await screen.findByTestId("insufficient-context");
    expect(notice).toHaveTextContent(INSUFFICIENT_ANSWER);
    expect(screen.queryByTestId("access-denied")).not.toBeInTheDocument();
    expect(screen.queryByText("Access Denied")).not.toBeInTheDocument();
  });

  it("renders authorized answers, source cards and citations exactly as before", async () => {
    signIn();
    mockFetch({ ...ME, [`POST ${PATH}`]: { body: ANSWERED } });
    renderApp("/app/chat");
    const user = await ask("What is the Finance department budget?");

    expect(await screen.findByText(ANSWERED.answer)).toBeInTheDocument();
    const sources = screen.getByRole("region", { name: "Sources retrieved for this answer" });
    await user.click(within(sources).getByRole("button", { name: /Nexora Finance Report FY 2025-26/ }));
    expect(screen.getByTestId("source-card")).toHaveTextContent("Similarity 0.82");
    expect(screen.queryByTestId("access-denied")).not.toBeInTheDocument();
  });

  it("shows the rate-limit error with Retry on HTTP 429, not the access-denied state", async () => {
    signIn();
    mockFetch({
      ...ME,
      [`POST ${PATH}`]: {
        status: 429,
        body: { error: { code: "HTTP_ERROR", message: "provider quota detail", request_id: "r" } },
      },
    });
    renderApp("/app/chat");

    await ask("What are the confidential HR salary bands?");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The assistant is busy");
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByTestId("access-denied")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("quota detail");
  });

  it("treats a missing documents:read permission (HTTP 403) as an error, not as a content denial", async () => {
    signIn();
    mockFetch({
      ...ME,
      [`POST ${PATH}`]: { status: 403, body: { error: { code: "HTTP_ERROR", message: "Permission denied.", request_id: "r" } } },
    });
    renderApp("/app/chat");

    await ask("What is the Finance department budget?");

    expect(await screen.findByRole("alert")).toHaveTextContent("Access restricted");
    expect(screen.queryByTestId("access-denied")).not.toBeInTheDocument();
  });

  it("lets the person keep asking after a denial, with the conversation preserved", async () => {
    signIn();
    let next: MockReply = reply("access_denied", DENIED_ANSWER);
    const fetchMock = mockFetch({ ...ME, [`POST ${PATH}`]: () => next });
    renderApp("/app/chat");

    await ask("What are the confidential HR salary bands?");
    await screen.findByTestId("access-denied");

    next = { body: ANSWERED };
    await ask("What is the Finance department budget?");

    expect(await screen.findByText(ANSWERED.answer)).toBeInTheDocument();
    expect(screen.getByTestId("access-denied")).toBeInTheDocument();
    expect(screen.getAllByRole("article", { name: "Nexora AI response" })).toHaveLength(2);
    expect(calls(fetchMock, "POST", PATH)).toHaveLength(2);
  });

  it("sends only the question: identity and permissions come from the token, not the browser", async () => {
    signIn();
    const fetchMock = mockFetch({ ...ME, [`POST ${PATH}`]: reply("access_denied", DENIED_ANSWER) });
    renderApp("/app/chat");

    await ask("What are the confidential HR salary bands?");
    await screen.findByTestId("access-denied");

    const [, init] = calls(fetchMock, "POST", PATH)[0];
    expect(Object.keys(JSON.parse(String(init?.body))).sort()).toEqual(["query", "top_k"]);
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer test-access-token");
  });

  it("does not turn an authorized-looking answer into a denial or the reverse", async () => {
    signIn();
    mockFetch({ ...ME, [`POST ${PATH}`]: reply("no_authorized_context", "I couldn't find any information.") });
    renderApp("/app/chat");

    await ask("Anything at all?");

    await waitFor(() => expect(screen.getByTestId("no-authorized-context")).toBeInTheDocument());
    expect(screen.queryByTestId("access-denied")).not.toBeInTheDocument();
  });
});
