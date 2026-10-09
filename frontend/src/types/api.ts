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

/** POST /api/v1/search/vector — results are already restricted to the caller's authorized documents. */
export interface VectorSearchRequest {
  query: string;
  top_k?: number;
}

export interface VectorSearchResult {
  chunk_id: string;
  document_id: string;
  chunk_index: number;
  page_number: number | null;
  source_locator: string | null;
  content: string;
  distance: number;
  similarity: number;
}

export interface VectorSearchResponse {
  query: string;
  top_k: number;
  distance_metric: "cosine";
  embedding_model: string;
  results: VectorSearchResult[];
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

/*
 * PROVISIONAL — POST /api/v1/assistant/query does NOT exist yet (backend Part 6).
 * This is the shape the UI is prepared to render; align it with the real contract
 * when Part 6 is implemented. Until then the client falls back to /search/vector.
 */
export interface AssistantQueryRequest {
  question: string;
}

export interface AssistantCitationDto {
  document_id: string;
  document_title: string;
  page_number: number | null;
  chunk_id: string;
  similarity?: number | null;
  excerpt?: string | null;
}

export interface AssistantQueryResponse {
  status: "answered" | "no_authorized_context";
  answer: string | null;
  citations: AssistantCitationDto[];
}
