import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { FINANCE_MANAGER, mockFetch, renderApp, signIn, type MockReply } from "@/test/utils";
import type { AssistantQueryResponse } from "@/types/api";

const PATH = "/api/v1/assistant/query";
const ME = { "GET /api/v1/auth/me": { body: FINANCE_MANAGER } };
const DENIED = "You don't have permission to access the information requested.";
const INSUFFICIENT = "The documents you're authorized to access don't contain enough information to answer this question.";

const SOURCE = {
  source_number: 1,
  document_id: "d1",
  document_title: "Nexora Finance Report FY 2025-26",
  chunk_id: "c1",
  page_number: 2,
  source_locator: "page:2",
  similarity: 0.82,
};

const TRUST = {
  authorization: "access_controlled_retrieval" as const,
  authorized_source_count: 1,
  provider: "groq",
  model: "openai/gpt-oss-120b",
};

function answered(extra: Partial<AssistantQueryResponse> = {}): MockReply {
  return {
    body: {
      status: "answered",
      answer: "The Finance budget for FY 2025-26 is INR 1.5 crore [S1].",
      request_id: "r1",
      sources: [SOURCE],
      unverified_source_numbers: [1],
      rejected_source_numbers: [],
      citation_check: "passed",
      trust_proof: TRUST,
      ...extra,
    },
  };
}

function nonAnswer(status: string, answer: string, extra: object = {}): MockReply {
  return {
    body: { status, answer, request_id: "r2", sources: [], unverified_source_numbers: [], rejected_source_numbers: [], citation_check: "not_applicable", trust_proof: null, ...extra },
  };
}

async function ask(reply: MockReply) {
  signIn();
  mockFetch({ ...ME, [`POST ${PATH}`]: reply });
  renderApp("/app/chat");
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Ask a question"), "What is the Finance budget?");
  await user.click(screen.getByRole("button", { name: "Send question" }));
  return user;
}

const receipt = () => screen.getByTestId("trustproof");
const toggle = () => within(receipt()).getByRole("button", { name: /TrustProof/ });

async function open(user: ReturnType<typeof userEvent.setup>) {
  await user.click(toggle());
  return within(receipt());
}

describe("TrustProof receipt: answered", () => {
  it("is collapsed by default and leaves the answer, sources and citations untouched", async () => {
    await ask(answered());
    await screen.findByText(/INR 1.5 crore/);
    expect(toggle()).toHaveAttribute("aria-expanded", "false");
    expect(within(receipt()).queryByText("Answer generated")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Sources retrieved for this answer" })).toHaveTextContent("Nexora Finance Report FY 2025-26");
    expect(screen.getByTestId("unverified-references")).toBeInTheDocument();
    expect(screen.getByText(/1 authorized source retrieved/)).toBeInTheDocument();
  });

  it("shows only server-verified facts when expanded (passed citations)", async () => {
    const user = await ask(answered());
    await screen.findByText(/INR 1.5 crore/);
    const r = await open(user);

    expect(toggle()).toHaveAttribute("aria-expanded", "true");
    expect(r.getByText("Answer generated")).toBeInTheDocument();
    expect(r.getByText("Access-controlled retrieval applied")).toBeInTheDocument();
    expect(r.getByText("Passed")).toBeInTheDocument();
    expect(r.getByText("1", { selector: "span" })).toBeInTheDocument();
    expect(r.getByText("Groq (cloud) · openai/gpt-oss-120b")).toBeInTheDocument();
    expect(receipt()).toHaveTextContent("does not verify that every statement in the answer is correct");
    await user.click(toggle());
    expect(toggle()).toHaveAttribute("aria-expanded", "false");
  });

  it("stays expanded while later messages arrive", async () => {
    const user = await ask(answered());
    await screen.findByText(/INR 1.5 crore/);
    await open(user);
    await user.type(screen.getByLabelText("Ask a question"), "And the HR budget?");
    await user.click(screen.getByRole("button", { name: "Send question" }));
    await waitFor(() => expect(screen.getAllByTestId("trustproof")).toHaveLength(2));
    expect(within(screen.getAllByTestId("trustproof")[0]).getByRole("button", { name: /TrustProof/ })).toHaveAttribute("aria-expanded", "true");
    expect(within(screen.getAllByTestId("trustproof")[1]).getByRole("button", { name: /TrustProof/ })).toHaveAttribute("aria-expanded", "false");
  });

  it("reports partial citation validation without hiding the answer", async () => {
    const user = await ask(answered({ citation_check: "partial", rejected_source_numbers: [9] }));
    await screen.findByText(/INR 1.5 crore/);
    const r = await open(user);
    expect(r.getByText("Partial")).toBeInTheDocument();
    expect(receipt()).toHaveTextContent("matched no source retrieved for you");
    expect(r.queryByText("Passed")).not.toBeInTheDocument();
  });

  it("shows the model that actually answered after a fallback", async () => {
    const user = await ask(answered({ trust_proof: { ...TRUST, provider: "lm_studio", model: "qwen/qwen3.5-9b" } }));
    await screen.findByText(/INR 1.5 crore/);
    const r = await open(user);
    expect(r.getByText("LM Studio (local) · qwen/qwen3.5-9b")).toBeInTheDocument();
    expect(r.queryByText(/Groq/)).not.toBeInTheDocument();
  });

  it("never invents what the server did not substantiate", async () => {
    const reply = answered();
    const body = reply.body as Record<string, unknown>;
    delete body.trust_proof;
    delete body.citation_check; // an older server
    const user = await ask(reply);
    await screen.findByText(/INR 1.5 crore/);
    const r = await open(user);

    expect(r.getByText("Answer generated")).toBeInTheDocument(); // the response itself is real
    expect(r.getAllByText("Not available")).toHaveLength(4); // authorization, citations, sources, model
    expect(r.queryByText("Access-controlled retrieval applied")).not.toBeInTheDocument();
    expect(r.queryByText("Passed")).not.toBeInTheDocument();
  });

  it("drops a receipt whose source count does not match the sources returned", async () => {
    const user = await ask(answered({ trust_proof: { ...TRUST, authorized_source_count: 3 } }));
    await screen.findByText(/INR 1.5 crore/);
    const r = await open(user);
    expect(r.queryByText("Access-controlled retrieval applied")).not.toBeInTheDocument();
    expect(r.queryByText("3")).not.toBeInTheDocument();
    expect(r.getAllByText("Not available").length).toBeGreaterThanOrEqual(3);
  });

  it("drops a receipt with the wrong authorization marker, and shows a missing provider as the model alone", async () => {
    const forged = await ask(answered({ trust_proof: { ...TRUST, authorization: "anything_else" as never } }));
    await screen.findByText(/INR 1.5 crore/);
    expect((await open(forged)).queryByText("Access-controlled retrieval applied")).not.toBeInTheDocument();
  });

  it("shows an unknown provider as the server reported it, and a missing one as the model only", async () => {
    const user = await ask(answered({ trust_proof: { ...TRUST, provider: null, model: "fake-llm" } }));
    await screen.findByText(/INR 1.5 crore/);
    expect((await open(user)).getByText("fake-llm")).toBeInTheDocument();
  });
});

describe("TrustProof receipt: states that are not an answer", () => {
  it("is absent for Access Denied, which keeps its fixed copy and shows nothing else", async () => {
    await ask(nonAnswer("access_denied", DENIED));
    const denied = await screen.findByTestId("access-denied");
    expect(within(denied).getByRole("heading", { name: "Access Denied" })).toBeInTheDocument();
    expect(denied).toHaveTextContent(DENIED);
    expect(screen.queryByTestId("trustproof")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Sources retrieved for this answer" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("insufficient-context")).not.toBeInTheDocument();
  });

  it("refuses a denial that carries a receipt, sources or metadata, and shows none of it", async () => {
    await ask(nonAnswer("access_denied", DENIED, { trust_proof: TRUST, sources: [{ ...SOURCE, document_title: "Restricted HR Policy" }] }));
    await screen.findByRole("alert");
    expect(screen.queryByTestId("trustproof")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("Restricted HR Policy");
    expect(screen.queryByTestId("access-denied")).not.toBeInTheDocument();
  });

  it("shows insufficient information as insufficient evidence, never as a denial or a verified answer", async () => {
    const user = await ask(nonAnswer("insufficient_context", INSUFFICIENT));
    expect(await screen.findByTestId("insufficient-context")).toHaveTextContent(INSUFFICIENT);
    const r = await open(user);
    expect(r.getByText("No answer generated")).toBeInTheDocument();
    expect(r.getByText("Insufficient")).toBeInTheDocument();
    expect(r.getByText("Not applicable")).toBeInTheDocument();
    expect(r.queryByText("Answer generated")).not.toBeInTheDocument();
    expect(r.queryByText("Access-controlled retrieval applied")).not.toBeInTheDocument();
    expect(screen.queryByTestId("access-denied")).not.toBeInTheDocument();
    expect(receipt()).not.toHaveTextContent(/denied|permission|restricted|incident/i);
  });

  it("has no receipt when no authorized context was found", async () => {
    await ask(nonAnswer("no_authorized_context", "No authorized information was found."));
    await screen.findByTestId("no-authorized-context");
    expect(screen.queryByTestId("trustproof")).not.toBeInTheDocument();
  });

  it("keeps the retry UI for a provider rate limit (429) and shows no receipt", async () => {
    await ask({ status: 429, body: { error: { code: "HTTP_ERROR", message: "quota detail", request_id: "r" } } });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The assistant is busy");
    expect(within(alert).getByRole("button", { name: /try again|retry/i })).toBeInTheDocument();
    expect(screen.queryByTestId("trustproof")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("quota detail");
  });

  it("shows no successful receipt for any failed request", async () => {
    for (const status of [500, 502, 504]) {
      const view = await ask({ status, body: { error: { code: "HTTP_ERROR", message: "detail", request_id: "r" } } });
      await screen.findByRole("alert");
      expect(screen.queryByTestId("trustproof")).not.toBeInTheDocument();
      expect(screen.queryByText("Answer generated")).not.toBeInTheDocument();
      expect(view).toBeDefined();
      document.body.innerHTML = "";
    }
  });

  it("has no receipt while the answer is still loading", async () => {
    signIn();
    mockFetch({ ...ME, [`POST ${PATH}`]: () => new Promise<MockReply>(() => {}) });
    renderApp("/app/chat");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Ask a question"), "What is the Finance budget?");
    await user.click(screen.getByRole("button", { name: "Send question" }));
    await waitFor(() => expect(screen.getByRole("status", { name: "" })).toBeInTheDocument());
    expect(screen.queryByTestId("trustproof")).not.toBeInTheDocument();
  });
});
