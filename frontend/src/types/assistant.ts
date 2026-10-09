/** UI-level model of an assistant reply, independent of which backend endpoint produced it. */

export interface Citation {
  id: string;
  /** Null when the backend does not return a document title (vector search). */
  title: string | null;
  pageNumber: number | null;
  similarity: number | null;
  excerpt: string | null;
}

export type AssistantResult =
  /** A generated answer with the sources it is grounded in. */
  | { kind: "answer"; answer: string; citations: Citation[] }
  /** Retrieval only: authorized passages, no generated answer (answer generation not enabled). */
  | { kind: "passages"; passages: Citation[] }
  /** The server found nothing this user is authorized to see for the question. */
  | { kind: "restricted" };
