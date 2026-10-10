/**
 * Wire types that mirror the backend OpenAPI schemas (backend/app/schemas/*).
 * Keep these in sync with the server; do not add fields the server does not send.
 */

/** POST /api/v1/auth/login */
export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

/** GET /api/v1/auth/me — the server's view of the signed-in user. */
export interface CurrentUser {
  id: string;
  email: string;
  full_name: string;
  roles: string[];
  permissions: string[];
}

/** The backend's global error envelope (app/core/exceptions.py). */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id: string;
    details?: { location: string; message: string }[];
  };
}

/**
 * POST /api/v1/assistant/query — the backend's RagQuery (backend/app/schemas/rag.py).
 * Unknown fields are rejected with 422; identity always comes from the bearer token.
 */
export interface AssistantQueryRequest {
  /** 1–2,000 characters after trimming. */
  query: string;
  /** Integer from 1 to 20; the server defaults to 5. */
  top_k?: number;
}

/**
 * "access_denied": the server itself (never the language model) established that the question targets
 * information the user may not read. It carries no sources, citations or document details.
 */
export type AssistantStatus = "answered" | "insufficient_context" | "no_authorized_context" | "access_denied";

/** An authorized passage the server gave the model: server metadata, not a validated citation. */
export interface AssistantSource {
  source_number: number;
  document_id: string;
  document_title: string;
  chunk_id: string;
  page_number: number | null;
  source_locator: string | null;
  /** Cosine similarity of the passage to the question; not a confidence score. */
  similarity: number;
  /** "pdf" or "image" (OCR text). Optional: absent from older servers. */
  source_type?: string;
}

/** One earlier turn of a document chat. Only these two roles exist; the server rejects anything else. */
export interface ChatTurnPayload {
  role: "user" | "assistant";
  content: string;
}

/** POST /api/v1/assistant/document-query. Identity comes from the bearer token; the server checks access to the document. */
export interface DocumentQueryRequest {
  document_id: string;
  query: string;
  /** At most 10 recent turns. Context for follow-ups only, never evidence. */
  history: ChatTurnPayload[];
}

/** The server's citation validation result: passed, partial (markers removed), none (cites nothing), not_applicable. */
export type CitationCheck = "passed" | "partial" | "none" | "not_applicable";

/**
 * What the server can substantiate about an answered query (backend TrustProof). Metadata only; it never
 * carries prompts, answers, passage text or hidden-source information.
 */
export interface TrustProofPayload {
  authorization: "access_controlled_retrieval";
  /** Number of final sources returned in `sources`. */
  authorized_source_count: number;
  provider: string | null;
  model: string | null;
}

export interface AssistantQueryResponse {
  status: AssistantStatus;
  /** The answer, or the server's fixed message when there is none. */
  answer: string;
  request_id: string;
  /** Empty unless status is "answered". */
  sources: AssistantSource[];
  /** The model's own [S<n>] references. UNVERIFIED until citation validation (backend Part 7). */
  unverified_source_numbers: number[];
  /** Numbers the model cited that matched no retrieved source (removed from the answer). Optional: absent from older servers. */
  rejected_source_numbers?: number[];
  /** Optional: absent from older servers. */
  citation_check?: CitationCheck;
  /** Present only for "answered"; null otherwise. Absent from older servers. */
  trust_proof?: TrustProofPayload | null;
}

/**
 * POST /api/v1/documents/ingest (201): the PDF was validated, extracted, chunked and stored,
 * and the server then tried to embed it. Only embedding_status "completed" means searchable.
 */
export interface DocumentIngestionResponse {
  document_id: string;
  filename: string;
  source_type: string;
  source_path: string;
  page_count: number;
  chunk_count: number;
  /** "processed" means stored and chunked; it does not mean embedded or searchable. */
  status: string;
  /** "completed", "failed" or "not_configured". Absent or null from a server that did not report it. */
  embedding_status?: string | null;
  /** The model that embedded the chunks; set when embedding_status is "completed". */
  embedding_model?: string | null;
}

/** POST /api/v1/embeddings/documents/{document_id} (200): chunks were embedded, so the document is searchable. */
export interface EmbeddingStorageResponse {
  document_id: string;
  chunks_processed: number;
  embeddings_created: number;
  embedding_model: string;
  status: string;
}

/** POST /api/v1/documents/ingest-image (201): the image was validated, read by OCR, chunked, stored and embedded. */
export interface ImageIngestionResponse {
  document_id: string;
  filename: string;
  source_type: string;
  source_path: string;
  chunk_count: number;
  ocr_line_count: number;
  /** The OCR engine's mean line confidence, 0 to 1. Not a measure of whether the text is correct. */
  ocr_mean_confidence: number;
  /** "completed", "failed" or "not_configured". Only "completed" means the text is searchable. */
  embedding_status: string;
  status: string;
}
