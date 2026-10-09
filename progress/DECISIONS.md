# Architecture Decision Log

## ADR-001: Authorization-first retrieval

**Status:** Accepted

The backend must apply document and row permissions inside the retrieval query. Unauthorized chunks must never be returned to the RAG orchestrator or LLM. Client-side filtering is not an authorization control.

## ADR-002: PostgreSQL with pgvector

**Status:** Accepted

PostgreSQL and pgvector provide relational metadata, access-policy predicates, and vector search in one database. The vector index must be paired with source and permission metadata.

## ADR-003: Provider adapters

**Status:** Accepted

Embedding and LLM providers will be accessed through backend interfaces selected by environment configuration. Provider-specific code will remain outside the core retrieval and authorization flow.

## ADR-004: Stable source citations

**Status:** Accepted

Every source uses a stable UUID and source-specific location. Model-generated citations are validated against the authorized source map and cannot override it.

## ADR-005: Untrusted content boundary

**Status:** Accepted

Retrieved PDF, OCR, and database content is untrusted input. It is isolated in the LLM context, must not be interpreted as instructions, and must not be able to change policy.

## ADR-006: Modular backend architecture

**Status:** Accepted

Authentication, authorization, ingestion, persistence, retrieval, provider adapters, and API orchestration will be separated into modules. This makes each security-sensitive behavior independently testable.

## ADR-007: Documentation-only initial state

**Status:** Accepted

No backend, frontend, dependencies, authentication, RAG, OCR, or database implementation will be created until the user explicitly approves Phase 1.

## ADR-008: Secure response contract

**Status:** Accepted

The API will return structured answers with validated citations. A response with missing or unauthorized citations will be rejected rather than returned to the user.

## ADR-009: Schema-first database migration

**Status:** Accepted

The ORM metadata is the source of truth for the Part 2.2 schema. Alembic generates a dedicated revision from that metadata, PostgreSQL schema inspection verifies the live result, and the revision is tested through downgrade and re-apply without application data.

## ADR-010: Embeddings stored on `document_chunks` with a fixed schema dimension

**Status:** Accepted

Embeddings live in a nullable `document_chunks.embedding vector(1536)` column, so there is no separate chunk or vector table. The dimension is fixed by migration `466650ac5b92` and mirrored by `EMBEDDING_VECTOR_DIMENSION` in the model. `EMBEDDING_DIMENSION` must equal it, and the provider factory fails fast otherwise. Changing to a model with another dimension requires a new migration. Vectors are never truncated or padded.

## ADR-011: OpenAI `text-embedding-3-small` as the single embedding provider

**Status:** Accepted

The configured default is the OpenAI provider (`text-embedding-3-small`, 1536 dimensions, batch size 100) behind the `EmbeddingProvider` interface (ADR-003). The API key comes only from `OPENAI_API_KEY`. Provider exception text is never logged or returned, because it can echo request details. Each chunk records `embedding_model`, and search only compares against chunks from the configured model, so vectors from incompatible models are never mixed.

## ADR-012: Cosine distance, exact search, no ANN index yet

**Status:** Accepted

Similarity search orders by pgvector cosine distance (`<=>`). The API returns `distance` (cosine distance, 0–2, lower is closer) and `similarity` (`1 - distance`), labelled explicitly. No HNSW/IVFFlat index is created yet: exact search is correct and deterministic at the current data size, and approximate indexes return fewer than K rows when Part 5 adds authorization predicates to the same query. Add an HNSW `vector_cosine_ops` index (with pgvector iterative scans) when data volume requires it.

## ADR-013: Migration does not drop the `vector` extension

**Status:** Accepted

The upgrade runs `CREATE EXTENSION IF NOT EXISTS vector`. The downgrade drops only the embedding columns. The extension is a database-level prerequisite that may be owned by a superuser (locally it is), so dropping it from an application migration would fail or be destructive.

## ADR-014: Deterministic synthetic demo dataset marked by UUIDv5 identifiers

**Status:** Accepted

The Nexora demo dataset is declared in code (`backend/demo_dataset/`) and has no randomness or timestamps. Every demo record's ID is a UUIDv5 under a fixed namespace, and PDFs are byte-identical across runs. "Is this a demo record?" therefore means "is its ID in the demo ID set", with no schema marker column. Generation is create-or-complete and never deletes. Reset deletes only demo IDs and refuses to run while non-demo data is linked to demo data.

## ADR-015: Explicit, default-deny access matrix as data

**Status:** Accepted

Document access exists only as explicit `document_role_access` / `document_user_access` rows, including grants for PUBLIC and INTERNAL documents. Department, classification and filename never imply access. `access_matrix.json` is generated from the same spec as the database grants, and tests assert that the two are equal, so Part 5 can enforce exactly what the database stores.

## ADR-016: Demo PDFs use the existing ingestion pipeline; embeddings are opt-in

**Status:** Accepted

Demo PDFs are ingested through `ingest_pdf`, which gained an optional `document_id` for deterministic IDs and refuses to overwrite an existing stored file. Chunking is never duplicated. Dataset generation never calls an external embedding API. `--with-embeddings` uses the existing Part 4 service and fails before any write if it is not configured.

## ADR-017: Separate test database

**Status:** Accepted

The backend test suite runs against `rag_system_test`, because several existing tests delete all documents. The development database `rag_system` holds the demo dataset.

## ADR-018: Password authentication with Argon2id and short-lived HS256 JWTs

**Status:** Accepted

Passwords are stored only as Argon2id hashes (argon2-cffi defaults, RFC 9106) in a nullable `users.password_hash`; NULL means the user cannot sign in. Login failures (unknown email, wrong password, inactive account, no password) return one identical 401, and unknown emails still spend a full hash verification. Access tokens are HMAC-signed JWTs (default HS256, 30 minutes) carrying only `sub`, `type`, `iat` and `exp`. Decoding pins the configured algorithm and requires all claims. `JWT_SECRET_KEY` is a SecretStr of at least 32 characters, required in production. There are no refresh tokens yet; clients sign in again.

## ADR-019: Server-side authorization on every request

**Status:** Accepted

Tokens carry no roles or permissions. On every request `get_current_user` reloads the user, rejects inactive or unknown accounts (so deactivation revokes existing tokens) and resolves roles and permissions from `user_roles` → `role_permissions`. Endpoints declare `require_permission(resource, action)`. Request fields such as `user_id` or `role` are never used for identity: schemas forbid them and query parameters are ignored.

## ADR-020: Document access is one SQL predicate, applied inside retrieval before LIMIT

**Status:** Accepted

`document_access_condition(user_id, document_id)` is the only definition of document access. It requires an active user plus an explicit grant: a `document_role_access` row for one of the user's roles (resolved in SQL), or a `document_user_access` row for the user. There is no department, classification, ownership or SUPER_ADMIN shortcut. The same predicate backs `can_access_document` and the vector search WHERE clause. PostgreSQL therefore applies authorization before ORDER BY/LIMIT: unauthorized chunks are never selected, never consume top-k slots and never reach Python. This is why exact search was kept (ADR-012). A future HNSW index must use pgvector iterative scans to keep filtered top-k complete.

## ADR-021: Default deny for uploads, with an explicit uploader grant

**Status:** Accepted

Preview and ingest require `documents:write` (SUPER_ADMIN only in the demo dataset). Ingestion records the uploader as owner and inserts a `document_user_access` row in the same transaction, so a new document is visible only to its uploader until further grants are added. Ownership itself never grants access. The embedding endpoint additionally requires access to the document and answers 404 otherwise, the same as for a missing document.

## ADR-022: Development-only demo credentials

**Status:** Accepted

Demo users receive an operator-chosen password (`DEMO_USER_PASSWORD`) through `scripts/set_demo_passwords.py`. No credential is hard-coded or stored in plaintext, only demo user IDs are touched, the script is idempotent, and it refuses to run with `APP_ENV=production`. The dataset generator never sets passwords.

## ADR-023: Groq as the answer-generation LLM, through the OpenAI-compatible API

**Status:** Accepted

Answer generation uses Groq (`openai/gpt-oss-120b` by default) through the existing `openai` SDK with `base_url=https://api.groq.com/openai/v1`, so no new dependency is needed. The provider sits behind `LLMProvider` (ADR-003) and returns only the final assistant text: reasoning traces are discarded, and provider error text is never logged or returned. Groq has no embeddings API, so embeddings remain a separate provider (ADR-011). The key is a SecretStr read only from the environment or the git-ignored `backend/.env`.

## ADR-024: Frontend is a thin client; the backend stays the only authority

**Status:** Accepted

The React client never decides access. It shows roles and permissions exactly as `/auth/me` returns them, has no role switcher, and treats a 403 or an empty authorized result as a non-leaking "access restricted" state. Route guards are UX only. The bearer token lives in `sessionStorage` (tab-scoped, survives reloads) and is attached only by `src/services/api.ts`. An httpOnly-cookie session would need backend changes. The Vite dev/preview proxy forwards `/api` to FastAPI, so no CORS change was made to the backend.

## ADR-025: Provisional assistant contract, real-search fallback, dev-only mock

**Status:** Accepted

The chat calls the planned `POST /api/v1/assistant/query` through an isolated client with clearly marked provisional types. While the server reports that route as missing, it falls back to the real, authorization-aware `/api/v1/search/vector` and shows authorized passages, never invented answers. `VITE_USE_MOCK_API=true` swaps in simulated responses for design previews in development builds only; production builds compile it out.

## ADR-026: Public hackathon demo accounts, server-authenticated

**Status:** Accepted

For presentations, six fixed, intentionally public demo credentials (one active seeded user per role) are set through the existing `set_demo_passwords.py` (`--hackathon-accounts`). They are stored as Argon2id hashes, validated against the dataset and database, and refused in production. The login page renders them from one frontend config whose cards only fill the form; authentication remains `POST /api/v1/auth/login`, and the displayed identity comes from `/auth/me`. A backend test keeps the frontend and backend lists identical. SUPER_ADMIN is displayed as "CEO / Super Admin" without changing backend role semantics.

## Future decisions

Architecture decisions that require selection during implementation include the exact authentication provider, OCR engine, LLM provider, deployment platform, and server-side rate-limiting policy.
