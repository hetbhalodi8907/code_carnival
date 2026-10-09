/**
 * Assistant client. Security decisions stay on the server: this module only sends the
 * question with the user's token and renders what comes back.
 *
 * 1. POST /api/v1/assistant/query (PROVISIONAL; backend Part 6 is not built yet).
 * 2. If the server reports that route as missing, fall back to the real, already
 *    authorization-aware POST /api/v1/search/vector and show the authorized passages.
 * 3. VITE_USE_MOCK_API=true (development builds only) swaps in a simulated assistant.
 */

import { USE_MOCK_ASSISTANT } from "@/config/env";
import { ApiError, api } from "@/services/api";
import type { AssistantQueryResponse, CurrentUser, VectorSearchResponse } from "@/types/api";
import type { AssistantResult } from "@/types/assistant";

const ASSISTANT_PATH = "/api/v1/assistant/query";
const SEARCH_PATH = "/api/v1/search/vector";
const SEARCH_TOP_K = 5;

/** Remember a missing assistant route so we do not send a wasted request per question. */
let assistantRouteAvailable: boolean | null = null;

export function resetAssistantRouteCache(): void {
  assistantRouteAvailable = null;
}

function fromAssistantResponse(response: AssistantQueryResponse): AssistantResult {
  if (response.status !== "answered" || !response.answer?.trim()) return { kind: "restricted" };
  return {
    kind: "answer",
    answer: response.answer.trim(),
    citations: response.citations.map((citation) => ({
      id: citation.chunk_id,
      title: citation.document_title,
      pageNumber: citation.page_number,
      similarity: citation.similarity ?? null,
      excerpt: citation.excerpt ?? null,
    })),
  };
}

function fromSearchResponse(response: VectorSearchResponse): AssistantResult {
  if (response.results.length === 0) return { kind: "restricted" };
  return {
    kind: "passages",
    passages: response.results.map((result) => ({
      id: result.chunk_id,
      title: null,
      pageNumber: result.page_number,
      similarity: result.similarity,
      excerpt: result.content,
    })),
  };
}

async function askServer(question: string, signal?: AbortSignal): Promise<AssistantResult> {
  if (assistantRouteAvailable !== false) {
    try {
      const response = await api.post<AssistantQueryResponse>(ASSISTANT_PATH, { question }, { signal });
      assistantRouteAvailable = true;
      return fromAssistantResponse(response);
    } catch (error) {
      if (!(error instanceof ApiError && error.isMissingRoute)) throw error;
      assistantRouteAvailable = false;
    }
  }
  const response = await api.post<VectorSearchResponse>(
    SEARCH_PATH,
    { query: question, top_k: SEARCH_TOP_K },
    { signal },
  );
  return fromSearchResponse(response);
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
  try {
    return await askServer(question, signal);
  } catch (error) {
    // The server refused (e.g. the account lacks documents:read): show the safe restricted state.
    if (error instanceof ApiError && error.status === 403) return { kind: "restricted" };
    throw error;
  }
}
