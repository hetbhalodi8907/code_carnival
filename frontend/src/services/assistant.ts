/**
 * Assistant client for POST /api/v1/assistant/query.
 *
 * Security decisions stay on the server: this module sends the question with the user's
 * token (through the shared API client) and renders what comes back. It never retrieves
 * anything itself. An assistant failure is reported as an error and is never replaced by
 * another endpoint's results, which would lose the grounding guarantees.
 *
 * VITE_USE_MOCK_API=true (development builds only) swaps in a simulated assistant.
 */

import { USE_MOCK_ASSISTANT } from "@/config/env";
import { api } from "@/services/api";
import type { AssistantQueryRequest, AssistantQueryResponse, AssistantSource, CurrentUser } from "@/types/api";
import type { AssistantResult } from "@/types/assistant";

const ASSISTANT_PATH = "/api/v1/assistant/query";
/** Sources retrieved per question (the server's default; the server allows 1–20). */
const ASSISTANT_TOP_K = 5;
const STATUSES: ReadonlySet<string> = new Set([
  "answered",
  "insufficient_context",
  "no_authorized_context",
  "access_denied",
]);

/** The server answered successfully, but not with a valid AssistantQueryResponse. */
export class UnexpectedResponseError extends Error {
  constructor() {
    super("The assistant returned an unexpected response.");
    this.name = "UnexpectedResponseError";
  }
}

function isSource(value: unknown): value is AssistantSource {
  if (!value || typeof value !== "object") return false;
  const source = value as Record<string, unknown>;
  return (
    Number.isInteger(source.source_number) &&
    typeof source.document_id === "string" &&
    typeof source.document_title === "string" &&
    typeof source.chunk_id === "string" &&
    (source.page_number === null || Number.isInteger(source.page_number)) &&
    (source.source_locator === null || typeof source.source_locator === "string") &&
    typeof source.similarity === "number" &&
    Number.isFinite(source.similarity)
  );
}

/** Accept only the documented contract; anything else is an error, never an answer. */
function parseResponse(payload: unknown): AssistantQueryResponse {
  const body = payload as Partial<Record<keyof AssistantQueryResponse, unknown>> | null;
  if (
    !body ||
    typeof body !== "object" ||
    typeof body.status !== "string" ||
    !STATUSES.has(body.status) ||
    typeof body.answer !== "string" ||
    !body.answer.trim() ||
    typeof body.request_id !== "string" ||
    !Array.isArray(body.sources) ||
    !body.sources.every(isSource) ||
    !Array.isArray(body.unverified_source_numbers) ||
    !body.unverified_source_numbers.every((number) => Number.isInteger(number))
  ) {
    throw new UnexpectedResponseError();
  }
  // A denial never carries sources or citations. If it does, the response is malformed and nothing
  // from it is shown.
  if (body.status === "access_denied" && (body.sources.length > 0 || body.unverified_source_numbers.length > 0)) {
    throw new UnexpectedResponseError();
  }
  return body as AssistantQueryResponse;
}

function toResult(response: AssistantQueryResponse): AssistantResult {
  const text = response.answer.trim();
  switch (response.status) {
    case "answered":
      return {
        kind: "answered",
        answer: text,
        // Server-derived metadata only; [S<n>] numbers are never mapped to these sources.
        sources: response.sources.map((source) => ({
          id: source.chunk_id,
          title: source.document_title,
          pageNumber: source.page_number,
          similarity: source.similarity,
        })),
        unverifiedSourceNumbers: [...response.unverified_source_numbers],
      };
    case "insufficient_context":
      return { kind: "insufficient_context", message: text };
    case "no_authorized_context":
      return { kind: "no_authorized_context", message: text };
    case "access_denied":
      // The denial is rendered from fixed copy; nothing the server sent with it is displayed.
      return { kind: "access_denied" };
  }
}

export async function askAssistant(
  question: string,
  user: CurrentUser,
  signal?: AbortSignal,
): Promise<AssistantResult> {
  if (USE_MOCK_ASSISTANT) {
    const { mockAskAssistant } = await import("@/mocks/mockAssistant");
    return mockAskAssistant(question, user, signal);
  }
  // Only the question and the retrieval size: identity comes from the bearer token.
  const request: AssistantQueryRequest = { query: question, top_k: ASSISTANT_TOP_K };
  const payload = await api.post<unknown>(ASSISTANT_PATH, request, { signal });
  return toResult(parseResponse(payload));
}
