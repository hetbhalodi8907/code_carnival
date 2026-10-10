/** UI-level model of an assistant reply, adapted from POST /api/v1/assistant/query. */

/** An authorized passage the server retrieved and gave the model. Not a verified citation. */
export interface RetrievedSource {
  /** The chunk ID. */
  id: string;
  title: string;
  pageNumber: number | null;
  /** Cosine similarity to the question; not a confidence score. */
  similarity: number;
}

export type AssistantResult =
  /** A grounded answer and the authorized sources the model was given. */
  | { kind: "answered"; answer: string; sources: RetrievedSource[]; unverifiedSourceNumbers: number[] }
  /** Authorized sources were found, but they do not answer the question. */
  | { kind: "insufficient_context"; message: string }
  /** No authorized source was found; the model was not called. */
  | { kind: "no_authorized_context"; message: string }
  /** The server determined the question targets information this user may not read. Carries no data. */
  | { kind: "access_denied" };
