# Project Progress

## Current phase

Part 5.1–5.3 (authentication, RBAC + authorization, retrieval-level security): complete. Next task: Part 6 (RAG engine), awaiting approval.

## Phase summary

- Part 1 — Backend foundation (1.1–1.10): complete.
- Part 2 — PostgreSQL + database (2.1–2.2): complete.
- Part 3 — PDF ingestion (3.1 intake/validation, 3.2 extraction/cleaning, 3.3 chunking/metadata, 3.4 persistent ingestion): complete.
- Part 4.1 — pgvector foundation: complete.
- Part 4.2 — Embedding provider + generation: complete.
- Part 4.3 — Vector storage + similarity retrieval: complete.
- Dataset Generation — synthetic Nexora demo dataset: COMPLETE.
- Part 5.1 — Authentication: complete.
- Part 5.2 — RBAC + authorization: complete.
- Part 5.3 — Retrieval-level security: complete.
- Frontend milestone 1 (basic demo-ready client): complete.
- Hackathon demo login experience: complete (six demo accounts, demo DB passwords set).
- Part 6.2 (provider layer only) — Groq LLM provider integrated and live-verified; no RAG pipeline or endpoint yet.

## Completed tasks

### Fix: blank white screen when starting the frontend

- [x] Root cause: the documented command `npm run dev      # http://localhost:5173` ended with a `#` note. macOS zsh does not treat `#` as a comment at an interactive prompt (`interactivecomments` is off), so npm ran `vite "#" "http://localhost:5173"`. Vite took `#` as the project root (`frontend/#`, which does not exist), loaded no `index.html` or config, and answered `GET /` with an empty 404 that the browser showed as a blank white page. The React code never ran.
- [x] Fix: `dev` and `preview` scripts pin the root (`vite .`, `vite preview .`), so stray arguments are ignored. Shell blocks in `README.md`, `frontend/README.md` and `backend/data/demo/README.md` contain no `#` comments, and each terminal has its own block.
- [x] Safety nets: `index.html` boot screen (themed, replaced by React on mount; explains a failed script load); `AppErrorBoundary` recovery screen ("Nexora encountered an unexpected UI error." / "Reload application") with no error details shown.
- [x] Backend-down login now says "Can't reach the Nexora server" (a bare 5xx from the dev proxy, without the backend's error envelope, is treated as unreachable).
- [x] Verified: the exact command typed into an interactive zsh now serves the app; 14 browser scenarios pass in Chromium, WebKit and Firefox and on the production preview; six-role E2E on `rag_system` passes; frontend 25/25, backend 185/185.

### Hackathon demo login experience

- [x] One active seeded user per role selected from the dataset (Ishaan Malhotra, Meera Iyer, Vikram Nair, Ananya Rao, Devika Krishnan, Kabir Sethi); inactive Farhan Qureshi excluded and still refused.
- [x] `demo_dataset/credentials.py`: `HACKATHON_ACCOUNTS` plus `set_hackathon_passwords` (Argon2id, validated against the spec and the DB, idempotent, six users only, refuses production); `scripts/set_demo_passwords.py --hackathon-accounts`.
- [x] Demo DB `rag_system`: the six hackathon passwords are set (6 hashes; dataset still verifies).
- [x] `backend/.env` (git-ignored) now has a random `JWT_SECRET_KEY`; tests that build `Settings()` use `_env_file=None`.
- [x] Frontend: demo account cards (role icons and colours, fill only), derived selection, "Log in as <role>", show/hide password, role labels (SUPER_ADMIN shown as "CEO / Super Admin"), sidebar identity card with "Authenticated", visible Log out.
- [x] Tests: backend 185/185 (includes frontend/backend credential sync); frontend 21/21; browser E2E: all six accounts log in through the real API on `rag_system`, the inactive user is refused, and the role demo flow was verified through the real authorization path (harness on `rag_system_test` with offline embeddings).

### Frontend milestone 1: demo-ready client (`frontend/`)

- [x] React 19 + TypeScript 5.9 + Vite 7 + Tailwind 4 + shadcn/ui-style components + React Router 7; design system in `frontend/DESIGN_SYSTEM.md` (dark-first, light theme).
- [x] Routes: `/login`, `/app/chat`, `/app/profile`; UX-only route guard.
- [x] Auth: login, then `/auth/me`; token in sessionStorage handled only by the central API client; 401/expiry triggers sign-out with a notice; sign-out clears all state.
- [x] Chat: empty state with example cards, quick prompts (fill only), loading, answer + citation chips/source cards, access-restricted (non-leaking), friendly error states.
- [x] Assistant client: provisional `/api/v1/assistant/query`, falling back to the real authorization-aware `/api/v1/search/vector` while the route is missing; dev-only mock (`VITE_USE_MOCK_API`), compiled out of production builds.
- [x] Vite dev/preview proxy for `/api` (the backend has no CORS); no backend files changed.
- [x] 16 frontend tests pass; typecheck, lint (0 problems) and production build OK; `npm audit` reports 0 vulnerabilities.
- [x] Browser-verified with Playwright against the real backend (test DB) at 1440/820/390 px: no page errors, no React warnings, no horizontal overflow.

### Groq LLM provider integration (Part 6.2 provider layer only)

- [x] Settings `GROQ_API_KEY` (SecretStr), `LLM_PROVIDER=groq`, `LLM_MODEL` (default `openai/gpt-oss-120b`), `LLM_BASE_URL`, `LLM_TEMPERATURE`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_TIMEOUT_SECONDS`.
- [x] `app/services/llm/provider.py`: `LLMProvider` abstraction plus `OpenAICompatibleLLMProvider` (existing `openai` SDK pointed at Groq). It validates messages and responses, returns only the final text (model reasoning is dropped), and never logs or returns provider error text.
- [x] Key stored only in git-ignored `backend/.env` (mode 600). It is not in code, docs, tests or logs.
- [x] `scripts/check_llm_provider.py`: live check passed (`openai/gpt-oss-120b`, ~1 s).
- [x] Groq account models checked: chat and prompt-guard models only, no embedding models.
- [x] 10 offline provider tests; full suite 178/178 on `rag_system_test`; live server check passed.

### Part 5 — Authentication, authorization, retrieval-level security

- [x] 5.1: `users.password_hash` (migration `7c3e9a1d5b20`, nullable; NULL means the user cannot sign in), Argon2id hashing (argon2-cffi).
- [x] 5.1: JWT settings (`JWT_SECRET_KEY` as SecretStr, at least 32 characters, required in production; `JWT_ALGORITHM` HS256/384/512; expiry 30 minutes). Tokens carry only `sub`, `type`, `iat`, `exp`, and decoding pins the algorithm.
- [x] 5.1: `POST /api/v1/auth/login` (indistinguishable 401 for wrong password, unknown email or inactive account, with timing equalised) and `GET /api/v1/auth/me`.
- [x] 5.1: `get_current_user` validates the bearer token and reloads the active user from the database on every request, so deactivation revokes existing tokens.
- [x] 5.1: Development-only `scripts/set_demo_passwords.py` (operator-chosen password, hashes only, demo users only, idempotent, `--clear`, refuses production).
- [x] 5.2: Centralized authorization (`app/services/authorization.py`): roles and permissions from the database, `require_permission(resource, action)`, `can_access_document`. Default deny with explicit role and user grants only; no SUPER_ADMIN bypass.
- [x] 5.2: Protected endpoints: search needs `documents:read`; preview, ingest and embedding need `documents:write`; embedding also needs document access (404 otherwise). Ingest grants the uploader explicit access in the same transaction.
- [x] 5.3: `VectorSearchService` requires `user_id`. The document access predicate is part of the SQL WHERE clause and is evaluated before ORDER BY/LIMIT.
- [x] 5.3: Mutation-tested: removing the predicate, or filtering in Python after LIMIT, makes the retrieval-security tests fail.
- [x] Error handler now preserves `WWW-Authenticate` headers (same error format).
- [x] Dev database `rag_system` upgraded to `7c3e9a1d5b20`; demo dataset unchanged and `--verify-only` passes. No demo passwords set there (operator's choice).
- [x] Full backend suite on `rag_system_test`: 168 tests, 168 passed, 0 failed, 0 skipped.

### Dataset Generation — Nexora Technologies demo dataset

- [x] Deterministic generator `backend/scripts/generate_demo_dataset.py` (package `backend/demo_dataset/`). It can generate, verify only, reset demo data, and optionally embed.
- [x] Database: 5 departments, 6 roles, 11 permissions, 29 role-permission links, 20 users (1 inactive), 20 user-role assignments.
- [x] PDFs: 10 synthetic documents (45 pages, 45 chunks) in `backend/data/demo/documents/`, ingested through the existing `ingest_pdf` pipeline.
- [x] Access: 29 explicit `document_role_access` grants and 2 `document_user_access` grants (default deny).
- [x] Manifests: `dataset_manifest.json`, `access_matrix.json`, and `test_scenarios.json` (23 scenarios) in `backend/data/demo/manifests/`.
- [x] Demo records use UUIDv5 IDs under a fixed namespace; reset deletes only those IDs and refuses to run when non-demo data is linked to demo data.
- [x] Idempotency verified: the second run creates and updates nothing and writes no files.
- [x] Database verification: the dev database `rag_system` matches the manifest files (`--verify-only` passes).
- [x] PDF verification: valid, expected page counts, titles and headings, extractable text, byte-identical rebuilds, and every key fact on exactly its declared page.
- [x] Access-matrix verification: database grants equal `access_matrix.json`, and scenario expectations agree with the matrix.
- [x] `ingest_pdf` gained an optional `document_id` and refuses to overwrite an existing stored PDF.
- [x] Dedicated test database `rag_system_test` created and migrated, so the test suite no longer wipes dev data.
- [x] No embeddings generated and no external API calls made (`--with-embeddings` is opt-in).
- [x] Full backend suite on `rag_system_test`: 119 tests, 119 passed, 0 failed, 0 skipped.

### Part 4 — pgvector, embeddings, vector search

- [x] Inspected the partial Part 4 implementation left by the previous agent and kept its structure.
- [x] Fixed the broken `from pgvector import to_text` import that prevented `app.main` from importing (all API tests were failing).
- [x] Migration `466650ac5b92`: `CREATE EXTENSION IF NOT EXISTS vector`, `document_chunks.embedding vector(1536)`, `document_chunks.embedding_model varchar(200)`.
- [x] Fixed the migration downgrade, which failed because the app role does not own the `vector` extension; downgrade now drops only the columns.
- [x] Single schema dimension constant `EMBEDDING_VECTOR_DIMENSION` used by the model; the provider factory rejects an `EMBEDDING_DIMENSION` that differs from it.
- [x] Embedding provider abstraction with one OpenAI provider; single and batch embedding; malformed, non-numeric, non-finite, count, and dimension validation; provider error details are never logged or returned.
- [x] `EMBEDDING_BATCH_SIZE` is now applied by `EmbeddingService`.
- [x] Transactional per-document embedding persistence recording `embedding_model`; any failure persists nothing.
- [x] Cosine-distance top-K search via pgvector `<=>`, restricted to chunks embedded by the configured model; returns `distance` and `similarity = 1 - distance`.
- [x] APIs: `POST /api/v1/embeddings/documents/{document_id}` and `POST /api/v1/search/vector` with safe 404/422/502/503 errors.
- [x] Migration upgrade → downgrade → upgrade verified on live PostgreSQL 15.17 + pgvector 0.8.7.
- [x] Full backend suite: 98 tests, 98 passed, 0 failed, 0 skipped.
- [x] Live server check of `/`, health, readiness, Swagger, PDF preview, PDF ingestion, and both Part 4 endpoints.

### Parts 1–3

- [x] Inspect the empty workspace.
- [x] Create the project README and documentation index.
- [x] Document project requirements and non-functional requirements.
- [x] Document the planned architecture and deployment shape.
- [x] Document technology choices and dependency policy.
- [x] Document end-to-end and ingestion data flows.
- [x] Document authentication, authorization, citation, and prompt-injection controls.
- [x] Define the planned API contract.
- [x] Define the planned PostgreSQL and pgvector schema.
- [x] Define the secure RAG and citation-validation design.
- [x] Create the phased development roadmap.
- [x] Create the minimal FastAPI application package.
- [x] Add the root endpoint returning the backend-running message.
- [x] Add FastAPI and Uvicorn requirements.
- [x] Add an isolated backend virtual environment.
- [x] Verify Python syntax and the running application endpoints.
- [x] Add centralized Pydantic settings for application metadata.
- [x] Add the safe `.env.example` file with no secrets.
- [x] Ensure `.env` is ignored while `.env.example` remains trackable.
- [x] Connect FastAPI application name and version to settings.
- [x] Add three focused configuration tests using the standard library.
- [x] Verify settings defaults, environment overrides, boolean parsing, CORS loading, application startup, root endpoint, and Swagger.
- [x] Add a centralized standard-library logging module using the existing `LOG_LEVEL` setting.
- [x] Configure a readable timestamp, level, logger/module, and message format.
- [x] Add a minimal application startup log without request or sensitive-data logging.
- [x] Add focused logging tests for level filtering, logger creation, application import, and startup.
- [x] Verify the application starts, GET / returns HTTP 200, Swagger returns HTTP 200, and all six tests pass.
- [x] Add UUID-based request IDs and request timing middleware.
- [x] Return the accepted request ID in the `X-Request-ID` response header.
- [x] Log only HTTP method, path, status, duration, and request ID.
- [x] Add centralized structured HTTP, validation, and unexpected-error handlers.
- [x] Add versioned health and readiness endpoints.
- [x] Add focused middleware, error-handling, and health/readiness tests.
- [x] Verify all 13 tests pass and the live API endpoints work.
- [x] Add a shared standard-library ASGI test helper for deterministic endpoint tests.
- [x] Add OpenAPI and API contract tests for public routes and metadata.
- [x] Capture expected error logging without noisy traceback output in tests.
- [x] Make the API version prefix come from centralized settings.
- [x] Keep the backend package structure focused and avoid unnecessary dependencies.
- [x] Validate application startup, all 17 tests, Python compilation, and live endpoint responses.
- [x] Confirm no editor diagnostics in backend or project-control files.
- [x] Add PostgreSQL configuration and safe local environment placeholders.
- [x] Add SQLAlchemy 2.x async engine, shared session factory, session dependency, and declarative base.
- [x] Add Alembic foundation and migration generation validation.
- [x] Add safe database connectivity checking and database-aware readiness.
- [x] Add database configuration, engine, session, dependency, connectivity, and readiness tests.
- [x] Verify application import, database-specific tests, readiness behavior, regression tests, compilation, and required endpoints.
- [x] Verify Alembic can generate the initial migration SQL without connecting to PostgreSQL.
- [x] Create the local `postgres` role and `rag_system` database without creating application data.
- [x] Verify live SQLAlchemy async connectivity with `SELECT 1`.
- [x] Verify the Alembic initial migration against the live `rag_system` database.
- [x] Verify the Alembic migration is idempotent when run again.
- [x] Verify `/`, `/api/v1/health`, `/api/v1/ready`, and `/docs` over the live application path.
- [x] Create the dedicated Part 2.2 Alembic revision `623078a250c3` from the ORM metadata.
- [x] Apply the Part 2.2 revision to the live `rag_system` database without application data.
- [x] Verify all 10 model tables, foreign keys, unique constraints, primary keys, and indexes in PostgreSQL.
- [x] Add focused schema metadata and live database tests.
- [x] Verify duplicate association assignments are rejected by PostgreSQL constraints.
- [x] Downgrade the Part 2.2 revision to `0001` and reapply it successfully.
- [x] Confirm Alembic reports `623078a250c3` as the current head.
- [x] Run all 32 backend tests successfully after the migration round trip.
- [x] Confirm no editor diagnostics in the new schema code or tests.
- [x] Part 3.1–3.4: PDF intake/validation, page-wise extraction and cleaning, deterministic page-local chunking with metadata, transactional document/chunk persistence, preview and ingest endpoints.

## Tasks in progress

- None.

## Pending tasks

- Phase 6 secure RAG (must call the authorization-aware `VectorSearchService` with the authenticated user).
- Phase 7 citations and grounding.
- Phase 8 structured database retrieval.
- Phase 9 OCR.
- Phase 10 AI assistant API.
- Phase 11 frontend.
- Phase 12 security testing.
- Phase 13 integration and demo.

## Known issues

- Row-level authorization for structured records is not implemented yet (Phase 8). There are no structured-record tables yet.
- No login rate limiting or account lockout yet (Phase 12 security hardening).
- **Before the live demo:** retrieval on `rag_system` still needs embeddings: Groq has no embeddings API, and `OPENAI_API_KEY` is not configured (0 of 45 demo chunks embedded).
- The Groq key was shared in chat; rotate it in the Groq console after the hackathon.
- Demo PDF filenames in `backend/data/documents/` are deterministic and shared by every database. Any ad-hoc `reset_dataset` or `generate_dataset` run against `rag_system_test` must set `DOCUMENT_STORAGE_PATH` to a temporary directory, as the test fixtures do. Otherwise it deletes `rag_system`'s stored PDFs. This happened once on 2026-10-09 (database untouched). The PDFs were restored from the checksummed artifacts in `backend/data/demo/documents/`, and `--verify-only` passes.
- Only the six hackathon demo accounts have passwords in `rag_system`; the other demo users get one only through `scripts/set_demo_passwords.py` with `DEMO_USER_PASSWORD`.
- No `OPENAI_API_KEY` is configured locally, so the OpenAI provider has been verified only with fake clients; without a key the Part 4 endpoints return a safe 503.
- Existing non-blocking warnings: PyMuPDF legacy `fitz` deprecation, and asyncpg unclosed-connection/socket warnings from the Part 3 PDF-ingest API test, which uses the global engine across event loops.
- Pre-existing Part 2.2 drift reported by `alembic check`: redundant `UniqueConstraint`s on association tables whose composite primary keys already enforce uniqueness. Not changed in Part 4.
- Live database tests need `DATABASE_URL` (never put it in `backend/.env`). Run them against the test database, because several existing tests delete **all** documents: `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_system_test .venv/bin/python -m unittest discover -s tests`. Running the suite against `rag_system` would delete the demo documents; restore them with `scripts/generate_demo_dataset.py`.

## Next immediate task

Part 5.1–5.3 is complete and verified. Part 6 (RAG engine) starts only after explicit approval.

## Last updated

2026-10-09

## Important implementation notes

- Part 1.1 implemented the minimal FastAPI skeleton and root endpoint only.
- Part 1.2 added centralized Pydantic settings, safe environment examples, environment-file protection, and focused configuration tests.
- Part 1.3 added a centralized standard-library logger configured from `LOG_LEVEL`, a readable format, and one startup log.
- Part 1.4 added UUID request IDs, request timing, and request metadata logging without body logging.
- Part 1.5 added centralized structured HTTP, validation, and unexpected-error responses with request IDs.
- Part 1.6 added versioned health and readiness endpoints based only on application initialization and configuration.
- Part 1.7 added deterministic standard-library testing helpers and clean expected-error logging.
- Part 1.8 kept the package focused and removed unnecessary test scaffolding while preserving the real ASGI behavior.
- Part 1.9 wired the configured API prefix and verified safe error and middleware behavior.
- Part 1.10 completed the full test, compilation, diagnostics, and live API verification cycle.
- FastAPI and Uvicorn are installed in the isolated backend virtual environment.
- Part 4 added pgvector embeddings, an OpenAI embedding provider, and technical (non-authorized) vector search. No authentication, authorization, RAG, OCR, LLM, citation, frontend, or demo data was added.
- The authorization boundary remains defined before RAG implementation.
- The remaining implementation phases are ordered to preserve the security boundary.
