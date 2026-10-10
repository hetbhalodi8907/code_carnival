/** UI-level model of an assistant reply, adapted from POST /api/v1/assistant/query. */

import type { CitationCheck } from "@/types/api";

/** Server-verified facts about one answered query. Only set when the server's receipt was complete and consistent. */
export interface TrustProofData {
  /** The count of final sources returned with the answer (equals the sources shown). */
  authorizedSourceCount: number;
  /** Provider that produced the answer after any fallback ("groq", "lm_studio"), or null if the server did not know. */
  provider: string | null;
  model: string | null;
}

/** An authorized passage the server retrieved and gave the model. Not a verified citation. */
export interface RetrievedSource {
  /** The chunk ID. */
  id: string;
  title: string;
  pageNumber: number | null;
  /** Cosine similarity to the question; not a confidence score. */
  similarity: number;
  /** "pdf" or "image" when the server reported it. Image (OCR) sources have no page number. */
  sourceType?: string;
}

export type AssistantResult =
  /** A grounded answer and the authorized sources the model was given. */
  | {
      kind: "answered";
      answer: string;
      sources: RetrievedSource[];
      unverifiedSourceNumbers: number[];
      /** The server's citation validation result; absent when the server did not report one. */
      citationCheck?: CitationCheck;
      /** Absent unless the server sent a complete receipt that matches the sources. Never reconstructed client-side. */
      trust?: TrustProofData;
    }
  /** Authorized sources were found, but they do not answer the question. */
  | { kind: "insufficient_context"; message: string }
  /** No authorized source was found; the model was not called. */
  | { kind: "no_authorized_context"; message: string }
  /** The server determined the question targets information this user may not read. Carries no data. */
  | { kind: "access_denied" };
