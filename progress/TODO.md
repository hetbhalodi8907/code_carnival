# Current TODOs

## Documentation and control

- [x] Inspect the workspace and preserve empty project state.
- [x] Create project and architecture documentation.
- [x] Create the requested API and database specification.
- [x] Create the phase roadmap and security requirements.
- [x] Create the progress tracker and decision log.
- [x] Record Phase 0 completion and Phase 1 as the next task.

## Phase 1 — Backend foundation

- [x] Create the minimal Python package structure.
- [x] Add the FastAPI application and root endpoint.
- [x] Add the minimum FastAPI and Uvicorn dependencies.
- [x] Add the isolated backend environment and startup instructions.
- [x] Verify import, startup, root response, and Swagger/OpenAPI.
- [x] Add centralized Pydantic settings for application metadata.
- [x] Add the safe `.env.example` file.
- [x] Ensure `.env` is ignored while `.env.example` remains trackable.
- [x] Connect FastAPI application name and version to settings.
- [x] Add focused configuration tests.
- [x] Verify settings defaults, overrides, booleans, CORS loading, startup, root response, and Swagger.
- [x] Add centralized standard-library logging configured from `LOG_LEVEL`.
- [x] Add a readable timestamp, level, logger/module, and message format.
- [x] Add one minimal application startup log.
- [x] Add focused logging tests and verify application startup.
- [x] Add UUID-based request IDs and request timing middleware.
- [x] Return request IDs through the `X-Request-ID` response header.
- [x] Log method, path, status, duration, and request ID without body logging.
- [x] Add centralized structured HTTP, validation, and unexpected-error handlers.
- [x] Add versioned health and readiness endpoints.
- [x] Add focused middleware, error-handling, and health/readiness tests.
- [x] Verify all existing and new behavior through unit and live API checks.
- [x] Add a shared standard-library ASGI test helper.
- [x] Add OpenAPI and API contract tests for public routes and metadata.
- [x] Capture expected error logging without noisy traceback output in tests.
- [x] Make the API version prefix come from centralized settings.
- [x] Keep the backend package focused and avoid unnecessary dependencies.
- [x] Run the complete test, compilation, diagnostics, and live API verification cycle.
- [ ] Add Pydantic request and response models.
- [ ] Add dependency and development commands.

## Phase 2 — PostgreSQL and database

- [x] Configure PostgreSQL settings and local environment placeholders.
- [x] Create the SQLAlchemy async engine, session factory, dependency, and declarative base.
- [x] Add Alembic foundation and validate initial migration SQL generation.
- [x] Add safe database connectivity checks and database-aware readiness.
- [x] Add database infrastructure tests and verify all non-live behavior.
- [x] Create the local `postgres` role and `rag_system` database without application data.
- [x] Verify live SQLAlchemy async connectivity with `SELECT 1`.
- [x] Verify the initial Alembic migration against the live database.
- [x] Verify the migration is idempotent and all required endpoints are available.
- [x] Create the Part 2.2 schema migration from ORM metadata.
- [x] Verify tables, constraints, primary keys, foreign keys, and indexes in PostgreSQL.
- [x] Add focused schema metadata and live database tests.
- [x] Verify duplicate associations are rejected and the migration round trip succeeds.
- [x] Run the complete backend test suite and confirm all 32 tests pass.
- [x] Configure PostgreSQL and pgvector (Part 4.1).
- [x] Add vector dimension configuration (Part 4.1).
- [x] Add a dedicated test database (`rag_system_test`; the dev database `rag_system` holds the demo dataset).

## Phase 3 — PDF ingestion

- [x] PDF intake and validation (Part 3.1).
- [x] Text extraction, normalization, and page metadata (Part 3.2).
- [x] Deterministic page-local chunking with metadata (Part 3.3).
- [x] Transactional document and chunk persistence with source provenance (Part 3.4).
- [x] Tests.

## Phase 4 — Embeddings and vector search

- [x] pgvector extension, `embedding vector(1536)` and `embedding_model` columns, migration round trip (Part 4.1).
- [x] Embedding provider abstraction, OpenAI provider, batching, validation (Part 4.2).
- [x] Persist embeddings with model metadata (Part 4.3).
- [x] Cosine-distance top-K vector search service and `POST /api/v1/search/vector` (Part 4.3).
- [x] Tests (unit, live pgvector, API).
- [ ] Live OpenAI verification once an `OPENAI_API_KEY` is supplied.
- [ ] Moved to Phase 5: permission-aware vector retrieval.

## Dataset Generation — Nexora demo dataset

- [x] Deterministic synthetic departments, roles, permissions, users and role assignments.
- [x] 10 synthetic multi-page PDFs ingested through the existing pipeline.
- [x] Explicit role and user document grants (default deny).
- [x] Dataset manifest, access matrix and security test scenarios.
- [x] Idempotent generator, verify-only mode and demo-only reset.
- [x] Dataset tests: PDFs, database, manifests, access matrix, idempotency, reset safety.
- [ ] Optional: run `--with-embeddings` once an `OPENAI_API_KEY` is available.

## Phase 5 — Authentication and authorization

- [x] Implement user authentication (Argon2id passwords, JWT, login, current user) (Part 5.1).
- [x] Implement role and permission resolution from the database (Part 5.2).
- [x] Enforce document access inside the vector retrieval query, before LIMIT (Part 5.3).
- [x] Log authentication/authorization decisions as categories only (no secrets, emails or tokens).
- [x] Add access-control tests (auth, RBAC, document access, retrieval security, scenarios).
- [ ] Row-level access for structured records (moves to Phase 8, when those records exist).
- [ ] Persistent authorization audit trail, e.g. `query_logs` (later phase).
- [ ] Login rate limiting / lockout (Phase 12).

## Phase 6 — Secure RAG

- [x] LLM provider layer: Groq via OpenAI-compatible API, live-verified (Part 6.2 provider only).
- [ ] Choose an embedding source for real data (OpenAI key, or a local embedding model); Groq has none.

- [ ] Implement the RAG orchestrator.
- [ ] Add configurable LLM provider adapter.
- [ ] Isolate untrusted retrieval content.
- [ ] Add prompt-injection regression tests.
- [ ] Verify unauthorized data never enters the LLM context.

## Phase 7 — Citations and grounding

- [ ] Define stable citation identifiers.
- [ ] Validate citations against authorized context.
- [ ] Reject unsupported factual claims.
- [ ] Add citation tests.

## Phase 8 — Structured database retrieval

- [ ] Implement structured record ingestion.
- [ ] Apply row-level permission predicates.
- [ ] Add record retrieval integration tests.

## Phase 9 — OCR

- [ ] Add image ingestion and OCR abstraction.
- [ ] Preserve OCR location metadata.
- [ ] Add OCR ingestion tests.

## Phase 10 — AI assistant API

- [ ] Add secure chat endpoint.
- [ ] Add request limits and logging.
- [ ] Add API integration tests.

## Phase 11 — Frontend

- [x] Milestone 1: demo-ready client (login, role display, secure chat, citations, restricted state, profile, themes, tests).
- [ ] Switch the assistant client to the real `/api/v1/assistant/query` contract once Part 6 lands (remove the provisional types).
- [ ] Show department once `/auth/me` exposes it; show document titles once retrieval returns them.

- [ ] Scaffold React and TypeScript.
- [ ] Add authentication and protected routes.
- [ ] Build the assistant interface.
- [ ] Add shadcn/ui components and Tailwind styling.
- [ ] Add frontend tests.

## Phase 12 — Security testing

- [ ] Test authorization bypasses.
- [ ] Test prompt injection.
- [ ] Test citation fabrication.
- [ ] Test malformed and oversized inputs.
- [ ] Test cross-user data leakage.
- [ ] Review remediation status.

## Phase 13 — Integration and demo

- [ ] Run Docker Compose integration tests.
- [ ] Validate all source types and access controls.
- [x] Add demonstration data and roles (synthetic Nexora dataset; OCR assets pending Phase 9).
- [ ] Create setup and usage documentation.
- [ ] Complete final verification.

## Gate before Phase 6

- [x] Parts 1–5 and the demo dataset implemented and verified; full backend suite passes (168/168).
- [x] Migration `7c3e9a1d5b20` upgrade/downgrade/re-upgrade verified on `rag_system_test`; `rag_system` upgraded with demo data intact.
- [x] No RAG, LLM, citation, OCR, or frontend created.
- [ ] Explicit user approval to begin Part 6.
