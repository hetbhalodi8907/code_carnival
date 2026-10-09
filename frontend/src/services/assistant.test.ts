import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api";
import { askAssistant, UnexpectedResponseError } from "@/services/assistant";
import type { AssistantQueryResponse } from "@/types/api";
import { FINANCE_MANAGER, calls, mockFetch, signIn } from "@/test/utils";

const PATH = "/api/v1/assistant/query";

const ANSWERED: AssistantQueryResponse = {
  status: "answered",
  answer: "The Finance department budget for FY 2025-26 is INR 1.5 crore [S1].",
  request_id: "req-1",
  sources: [
    {
      source_number: 1,
      document_id: "7f6a0000-0000-4000-8000-000000000001",
      document_title: "Nexora Finance Report FY 2025-26",
      chunk_id: "c0000000-0000-4000-8000-000000000001",
      page_number: 2,
      source_locator: "page:2",
      similarity: 0.82,
    },
  ],
  unverified_source_numbers: [1],
};

describe("assistant service", () => {
  it("POSTs the RagQuery body with the bearer token", async () => {
    signIn();
    const fetchMock = mockFetch({ [`POST ${PATH}`]: { body: ANSWERED } });

    await askAssistant("What is the Finance department budget?", FINANCE_MANAGER);

    const [[url, init]] = calls(fetchMock, "POST", PATH);
    expect(url).toBe(PATH);
    const headers = init?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer test-access-token");
    expect(headers["Content-Type"]).toBe("application/json");
    // `query`, not the old provisional `question`; no identity or role fields.
    expect(JSON.parse(String(init?.body))).toEqual({ query: "What is the Finance department budget?", top_k: 5 });
  });

  it("maps each documented status to its UI result", async () => {
    signIn();
    mockFetch({ [`POST ${PATH}`]: { body: ANSWERED } });
    expect(await askAssistant("q", FINANCE_MANAGER)).toEqual({
      kind: "answered",
      answer: ANSWERED.answer,
      sources: [{ id: ANSWERED.sources[0].chunk_id, title: "Nexora Finance Report FY 2025-26", pageNumber: 2, similarity: 0.82 }],
      unverifiedSourceNumbers: [1],
    });

    for (const status of ["insufficient_context", "no_authorized_context"] as const) {
      mockFetch({
        [`POST ${PATH}`]: {
          body: { status, answer: "  Fixed server message.  ", request_id: "r", sources: [], unverified_source_numbers: [] },
        },
      });
      expect(await askAssistant("q", FINANCE_MANAGER)).toEqual({ kind: status, message: "Fixed server message." });
    }
  });

  it("rejects bodies that do not match the contract instead of inventing an answer", async () => {
    signIn();
    const invalid: unknown[] = [
      null,
      "an answer",
      { ...ANSWERED, status: "ok" },
      { ...ANSWERED, status: undefined },
      { ...ANSWERED, answer: "   " },
      { ...ANSWERED, answer: null },
      { ...ANSWERED, request_id: 7 },
      { ...ANSWERED, sources: null },
      { ...ANSWERED, sources: [{ ...ANSWERED.sources[0], document_title: null }] },
      { ...ANSWERED, sources: [{ ...ANSWERED.sources[0], page_number: "2" }] },
      { ...ANSWERED, unverified_source_numbers: ["S1"] },
      { answer: "Old provisional shape", citations: [] },
    ];
    for (const body of invalid) {
      mockFetch({ [`POST ${PATH}`]: { body } });
      await expect(askAssistant("q", FINANCE_MANAGER)).rejects.toBeInstanceOf(UnexpectedResponseError);
    }
  });

  it("surfaces every server error and never falls back to plain search", async () => {
    signIn();
    for (const status of [403, 404, 422, 500, 502, 503, 504]) {
      const fetchMock = mockFetch({
        [`POST ${PATH}`]: { status, body: { error: { code: "HTTP_ERROR", message: "detail", request_id: "r" } } },
      });
      await expect(askAssistant("q", FINANCE_MANAGER)).rejects.toMatchObject({ status });
      expect(calls(fetchMock, "POST", "/api/v1/search/vector")).toHaveLength(0);
      expect(fetchMock).toHaveBeenCalledTimes(1);
    }
  });

  it("reports network failures as unreachable", async () => {
    signIn();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const failure = askAssistant("q", FINANCE_MANAGER);
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({ status: 0 });
  });
});
