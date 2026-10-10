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
import type {
  AssistantQueryRequest,
  AssistantQueryResponse,
  AssistantSource,
  ChatTurnPayload,
  CitationCheck,
  CurrentUser,
  DocumentQueryRequest,
} from "@/types/api";
import type { AssistantResult, TrustProofData } from "@/types/assistant";

const ASSISTANT_PATH = "/api/v1/assistant/query";
const DOCUMENT_QUERY_PATH = "/api/v1/assistant/document-query";
/** Earlier turns sent with a document question (the server accepts at most 10). */
export const MAX_HISTORY_TURNS = 10;
/** Sources retrieved per question (the server's default; the server allows 1–20). */
const ASSISTANT_TOP_K = 5;
const STATUSES: ReadonlySet<string> = new Set([
  "answered",
  "insufficient_context",
  "no_authorized_context",
  "access_denied",
]);

const CITATION_CHECKS: ReadonlySet<string> = new Set(["passed", "partial", "none", "not_applicable"]);

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
  // A denial never carries sources, citations or a receipt. If it does, the response is malformed and
  // nothing from it is shown.
  if (
    body.status === "access_denied" &&
    (body.sources.length > 0 || body.unverified_source_numbers.length > 0 || (body.trust_proof ?? null) !== null)
  ) {
    throw new UnexpectedResponseError();
  }
  return body as AssistantQueryResponse;
}

function optionalText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/**
 * The receipt is shown only when it is complete and consistent with what the user actually received:
 * the authorization marker is the expected one and the source count equals the sources returned. Anything
 * else is dropped (the UI then says "Not available"); nothing is guessed or filled in.
 */
function parseTrust(value: unknown, sourceCount: number): TrustProofData | undefined {
  if (!value || typeof value !== "object") return undefined;
  const proof = value as Record<string, unknown>;
  if (proof.authorization !== "access_controlled_retrieval") return undefined;
  if (!Number.isInteger(proof.authorized_source_count) || proof.authorized_source_count !== sourceCount) return undefined;
  return {
    authorizedSourceCount: proof.authorized_source_count as number,
    provider: optionalText(proof.provider),
    model: optionalText(proof.model),
  };
}

function parseCitationCheck(value: unknown): CitationCheck | undefined {
  return typeof value === "string" && CITATION_CHECKS.has(value) ? (value as CitationCheck) : undefined;
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
          ...(typeof source.source_type === "string" ? { sourceType: source.source_type } : {}),
        })),
        unverifiedSourceNumbers: [...response.unverified_source_numbers],
        citationCheck: parseCitationCheck(response.citation_check),
        trust: parseTrust(response.trust_proof, response.sources.length),
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

/**
 * Ask about ONE document. The server decides whether the signed-in user may read it (a missing and an
 * unreadable document look identical), retrieves only from that document, and answers from it. This is always
 * a real request: it is never simulated by the mock assistant.
 */
export async function askAboutDocument(
  documentId: string,
  question: string,
  history: ChatTurnPayload[],
  signal?: AbortSignal,
): Promise<AssistantResult> {
  const request: DocumentQueryRequest = {
    document_id: documentId,
    query: question,
    history: history.slice(-MAX_HISTORY_TURNS),
  };
  const payload = await api.post<unknown>(DOCUMENT_QUERY_PATH, request, { signal });
  return toResult(parseResponse(payload));
}
