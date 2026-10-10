# Project Progress

## Current phase

Part 6.3 (authenticated assistant query API): complete. Next task: awaiting instruction (Part 6.4 or Part 7 citation validation); not started.

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
- Part 6.1 — Query processing + secure context construction: complete (internal service; no LLM call, no new endpoint).
- Part 6.2 — Grounded LLM generation: complete (internal service over the existing Groq provider).
- Part 6.3 — Authenticated assistant query API: complete (`POST /api/v1/assistant/query`).

## Completed tasks

### Role-aware dashboard (2026-10-10)

- [x] `GET /api/v1/dashboard/overview` (`app/api/v1/dashboard.py`, `app/services/dashboard/service.py`, `app/schemas/dashboard.py`): read-only, database-side aggregation, no LLM, identity only from the verified token. Sections (`projects`, `finance`, `workforce`, `security`) are `null` unless the account holds the permission; documents are counted only through `document_access_condition`; the employee scope is projects they lead or are a member of; compensation is a record count only.
- [x] Additive migration `c3f6e9b2d5a4` (budgets, expenses, project members, milestones) and idempotent fictional seed (`demo_dataset/dashboard.py`, `scripts/seed_dashboard_data.py`). Applied to `rag_system_test` and `rag_system`; before and after counts for users, roles, permissions, grants, documents, chunks, embeddings and a password-hash checksum were identical.
- [x] Frontend `/app/dashboard` is the login destination and first sidebar item; Assistant and both upload pages unchanged.
- [x] Not stored, shown as "Not available": security events, activity feed, system health, workforce history, personal tasks.
- [x] Tests: `backend/tests/test_dashboard_api.py` (22), `frontend/src/pages/DashboardPage.test.tsx` (17). Full frontend suite 131 pass, tsc, eslint and build clean. Live check of all six demo logins on the real database and a real-browser run (desktop, tablet, mobile; no console errors).

### Optional LM Studio (Qwen) fallback

- [x] `FallbackLLMProvider` in `app/services/llm/provider.py` wraps the Groq provider and tries a local OpenAI-compatible LM Studio model once, only after a rate limit (429), timeout, HTTP 503 or connection failure (new `LLMProviderUnavailableError`). Auth, permission, request, validation and other server errors never trigger it. If the local attempt also fails, the original Groq error is raised, so the existing 429/504/502 behavior is unchanged. Off by default (`LM_STUDIO_ENABLED=false`). When on, the Groq client uses no SDK retries and no rate-limit wait, so failover is immediate.
- [x] Settings: `LM_STUDIO_ENABLED`, `LM_STUDIO_BASE_URL`, `LM_STUDIO_MODEL`, `LM_STUDIO_API_KEY` (optional), `LM_STUDIO_TIMEOUT_SECONDS`, `LM_STUDIO_MAX_OUTPUT_TOKENS`. Startup validation requires a model and a loopback URL when enabled. The Groq key is never sent to the local server. Inline `<think>` text from Qwen is stripped from answers.
- [x] No change to retrieval, authorization, prompts, citation validation, response schemas, embeddings, ingestion or the database. The local model receives exactly the messages the generation layer built from authorized context.
- [x] Tests: `test_llm_fallback.py` (15, mocked clients only); breaking the trigger rule makes 6 of them fail. Related existing tests pass: provider 12, generation 23, assistant API 24, config 3. The full backend suite was not rerun.
- [x] Real local inference verified once (no Groq): `qwen/qwen3.5-9b` on LM Studio at port 1235 answered a grounded question correctly with a valid citation in about 64 seconds (about 1,000 thinking tokens).
- [x] Local-only mode: `LLM_PROVIDER=lm_studio` makes `create_llm_provider()` return the plain local provider (no Groq key, no client, no fallback wrapper). Default stays `groq`, so rollback is one setting; no Groq code was removed. 20 new mocked tests in `tests/test_llm_local_only.py`.
- [ ] **Local-only is NOT showcase-ready:** two further real runs of `qwen/qwen3.5-9b` failed (thinking used the whole 2048- and then 4096-token budget; 87s and 165s; safe 502, nothing invented). Next step: turn thinking off for the model in the local app (or test a non-zero temperature), then re-measure.
- [ ] Not verified: the end-to-end switch with a real Groq 429 (covered only with mocks), and the fallback running inside the live backend and browser.

### Upload discoverability fix and live re-verification (2026-10-10)

- [x] **Cause of the "invisible upload UI":** `Sidebar.tsx` filtered the navigation by permission, so any account without `documents:write` (all but the CEO account) never saw the Upload or Upload images entries. The pages and the backend were fine, and the servers had simply been stopped after the previous audit.
- [x] **Fix (frontend only, no permission change):** both entries are shown to every signed-in account, marked with a lock plus accessible text for accounts lacking the permission; the two pages share a new `UploadLocked` state (permission explanation, "CEO / Super Admin currently has it", link back to the chat, no controls). Server-side authorization is unchanged. Permissions cannot flash while loading because the shell renders only after `/auth/me` returns.
- [x] Tests: `UploadAccess.test.tsx` (17 tests across Finance, HR, Employee and CEO) fails 9 of 17 when the old filter is restored; two older tests that asserted the hiding were updated. Frontend 104/104, typecheck, lint and build clean.
- [x] Real browser and API check passed 27 of 27 checks (see `backend/data/demo/README.md`, "Latest end-to-end check"); temporary documents were removed by exact ID and the demo database matched its baseline.

### Final backend-to-frontend compatibility audit

- [x] **Image page discrepancy resolved:** the frontend image upload page DOES exist (`ImageUploadPage.tsx`, `services/images.ts`, route `/app/upload-image`, nav entry "Upload images"; files dated 21:23 to 21:25). An earlier backend report and the first version of the runbook said it did not; that was stale and wrong, and the runbook is corrected.
- [x] **Contracts match:** every field of the six audited endpoints' response schemas (login token, current user, PDF ingest, image ingest, embeddings retry, assistant request and response) was compared programmatically against the frontend wire types: no missing or wrongly optional fields, multipart field `file` for both uploads, bearer auth, and the documented 400/413/422/502/503 handling. The frontend does not model four additive assistant fields (`citation_check`, `rejected_source_numbers`, `source_type`, `cited`), which it ignores safely.
- [x] **Live browser check** (real Vite dev server and proxy, real backend on `rag_system`, no Groq): CEO account uploaded a synthetic PDF (one request, no embeddings call, "Ready to search", indexed with the local model) and a synthetic PNG (one request, real OCR 4 lines at 99%, "Ready to search"); a fake image was refused with the server's message; the Finance Manager sees no upload navigation and the pages show "isn't available" with no request sent. Temporary records (4 PDFs from repeated runs, 1 PNG) and files were deleted, and a before/after snapshot of users, password hashes, roles, permissions, documents, chunk text, embeddings, grants and structured tables was identical.
- [x] Frontend 429 handling was added afterwards by the frontend session ("The assistant is busy"); it is present in the code but was not exercised live.
- [x] Final handoff: `backend/data/demo/README.md` now has a "Verification status" section (live browser, API, previously reported tests, unverified items, Groq quota). Nothing was re-executed. Remaining known risk: the Groq free-tier quota.
- [ ] Not re-run: backend suite (last 325/325) and frontend suite (not touched in this audit); no Groq calls were made (quota).

### Submission verification (backend) and rate-limit handling

- [x] End-to-end check on `rag_system` (in-process app, real login, real local embeddings, real OCR, real Groq `openai/gpt-oss-120b` with a recording wrapper): existing Finance Q&A answered with every source matching its database chunk (document, title, page, locator); a synthetic PDF uploaded as SUPER_ADMIN was extracted into 2 page chunks, embedded at 384 dimensions, granted to the uploader only, and answered with `page:2` source metadata; a synthetic PNG was read by real OCR (5 lines, mean confidence 0.98), embedded, indexed and answered with an `image` source; the structured headcount question was answered from structured rows. Five other demo accounts asked 3 questions each (15 requests): no temporary document ID or text appeared in any response or in the SOURCES sent to Groq (the same scan detected the secrets in the CEO's own prompts). All temporary rows and files were then deleted; counts and checksums of users, password hashes, roles, permissions, documents, chunk content and embeddings, grants and structured tables matched the baseline exactly.
- [x] Found: Groq free-tier limits (8,000 tokens/minute, daily token allowance). Heavy repeated testing exhausted the daily allowance (`retry-after` about 10 minutes), and rate limits surfaced as a generic 502. Fix: `LLMProviderRateLimitError`; the provider waits once for a short `Retry-After` (`LLM_RATE_LIMIT_MAX_WAIT_SECONDS`, default 45), otherwise the assistant returns HTTP 429 with a fixed message. Unit-tested; the live short-wait path was not exercised because the daily limit was already exhausted at that point.
- [x] Focused tests after the fix: provider 12, generation 23, assistant API 24, unified 7, PDF upload 5, all passing. Full suite after the change: 325/325 passed, 0 skipped.
- [x] Submission runbook written in `backend/data/demo/README.md` (environment, PostgreSQL, backend, frontend pointer, login, PDF and image upload, questions, limitations, recovery).
- [ ] Open: avoid heavy rehearsal before the presentation; the free Groq allowance resets on a rolling basis.

### Parts 7–10 and PDF upload indexing (backend)

- [x] **Part 7 citations:** `app/services/rag/citations.py` normalizes `[S1]`, `【S1】`, `［S1］`, `[S1, S2]` to ASCII `[S<n>]`, removes markers that match no source retrieved for the request (reported as `rejected_source_numbers`), and replaces fabricated UUIDs. `citation_check` is passed/partial/none; each source has `cited` and `source_type`. A surviving marker proves the source exists and was authorized, not that it supports the sentence: claim-level verification is NOT implemented. All response additions are optional, so the frontend contract still holds.
- [x] **Part 8 structured retrieval:** tables `projects` and `employee_compensation` (migration `b2e5d8a1c4f3`, reversible, verified on the test DB first). A deterministic router (no LLM-written SQL) maps questions to six fixed intents: headcount by department, department projects, employee directory, own profile, own compensation, named employee compensation. Row-level access is in each statement's WHERE: directory data needs an active user with `documents:read`; compensation needs the employee's own row or `hr:read`. Tests show it equals the document access matrix for every user. Seed: `scripts/seed_structured_data.py` (8 projects, 2 compensation rows matching the existing statements).
- [x] **Part 9 OCR:** `POST /api/v1/documents/ingest-image` (`documents:write`; PNG/JPEG, magic bytes, `MAX_IMAGE_SIZE_MB`, `MAX_IMAGE_PIXELS`). RapidOCR (`rapidocr-onnxruntime`, pip only, no OS install) -> existing chunker -> shared `persist_document` (uploader-only grant) -> local embeddings. Empty text 422, missing engine 503. OCR text is retrieved as an ordinary document (`source_type="image"`). Demo: `scripts/seed_structured_data.py --with-ocr`.
- [x] **Part 10 unified assistant:** `UnifiedContextBuilder` routes structured intents first, and falls back to authorization-aware document search (PDF and OCR) when there is no intent or no authorized row. The `/assistant/query` contract is unchanged apart from optional additions.
- [x] **PDF upload indexing:** `POST /api/v1/documents/ingest` now embeds the document right after persisting it (`embedding_status`, `embedding_model` in the response), so it is searchable at once, by its uploader only. An embedding failure keeps the upload and reports `failed`/`not_configured`; `POST /embeddings/documents/{id}` can retry.
- [x] Verified: backend 324/324, 0 skipped. Live on `rag_system` with real Groq: finance, HR-denied, structured headcount and Rahul-denied questions; the OCR notice and structured rows seeded into the demo DB (additive). A synthetic PDF upload was answered for its uploader with `page:2` sources and was invisible to Finance, HR and Employee accounts; it was removed afterwards and the demo DB returned to its baseline.

### Local embeddings (no OpenAI key) and live end-to-end verification

- [x] New Groq key stored only in the git-ignored `backend/.env` (mode 600), replacing the previous key; never printed.
- [x] `sentence-transformers` 5.7.0 (torch 2.14.1) installed; `requirements.txt` now lists `sentence-transformers>=3.0,<6.0`. The first install attempt timed out downloading torch and changed nothing; the retry with `UV_HTTP_TIMEOUT=600 UV_HTTP_RETRIES=5` succeeded.
- [x] `SentenceTransformerEmbeddingProvider`: the local `sentence-transformers/all-MiniLM-L6-v2` model (384 dimensions, CPU, normalized), loaded once per process and run in a worker thread. It is the default provider; OpenAI remains optional and requests 384 dimensions.
- [x] Migration `a1d4c7e9f3b2`: `document_chunks.embedding` from `vector(1536)` to `vector(384)`, clearing incompatible vectors and their model labels first (downgrade reverses this). Verified upgrade, downgrade and re-upgrade on `rag_system_test`; a seeded 1536-dimension vector was cleared, not mis-cast.
- [x] `rag_system` migrated with users, passwords, roles, permissions, documents, chunks (content checksum) and grants unchanged. `generate_demo_dataset.py --with-embeddings` embedded all 45 chunks: one model, 384 dimensions, unit norm, 45 distinct vectors. A rerun embedded nothing; re-embedding stored chunks with the query-time service reproduced them exactly (cosine 1.0).
- [x] Live `POST /api/v1/assistant/query` (real login, Groq `openai/gpt-oss-120b`):
  - Finance Manager, finance question: answered (INR 1.5 crore), sources from Finance and Procurement reports;
  - Finance Manager, HR salary bands: `insufficient_context`, no sources;
  - Kabir, own CTC: answered (INR 11.4 lakh) from his own statement;
  - Kabir, Rahul's CTC: `insufficient_context`.

  Every source was within the access matrix. An invalid Groq key gave 502 "The language model request failed." and a missing local model gave 502 "The embedding provider could not generate embeddings."; no key, header, question or password appeared in any log.
- [x] Tests: backend 275/275, 0 skipped (adds local-provider unit tests and a real cached-model test); frontend 35/35, typecheck, lint and build clean.

### Frontend: chat aligned with the assistant query API

- [x] `src/services/assistant.ts` sends `{query, top_k: 5}` to `POST /api/v1/assistant/query` through the existing API client (bearer token, JSON, 401 session expiry). It accepts only the documented `AssistantQueryResponse`; any other body is an error.
- [x] Removed the provisional 404 fallback to `/search/vector`, so assistant failures are shown and never replaced by ungrounded search results. The provisional types and `ApiError.isMissingRoute` were removed too.
- [x] All three statuses are rendered with the server's own messages. Sources show title, page and similarity (plain cosine score). `[S<n>]` stays unverified text and is not linked to any source.
- [x] Errors: status-specific copy for 403, 422, 500, 502, 503, 504 and network failures; Retry for temporary failures re-asks in place (no duplicate messages); one request at a time.
- [x] The dev-only mock now matches the real contract and remains compiled out of production builds.
- [x] Tests: frontend 35/35 (assistant service 5, chat 10, API client 6, plus existing). Frontend mutation checks (old `question` field, silent search fallback, similarity as a percentage, duplicating retry, unvalidated bodies) were each caught. Typecheck, lint, build and `npm audit` are clean. Browser check against the real backend: the request is accepted and gets HTTP 503 (no embeddings), shown as a retryable error; layouts verified on desktop and mobile with intercepted responses. No backend files changed.

### Part 6.3 — Authenticated assistant query API

- [x] `POST /api/v1/assistant/query` (`app/api/v1/assistant.py`) is a thin route over existing services: `require_permission("documents", "read")` (the JWT current-user dependency), the `RagQuery` body, `create_context_builder`, then `create_answer_generator`. No new auth, retrieval, provider or prompt logic.
- [x] Auth, permission and body validation run before the route: 401 without a valid token or for an inactive account, 403 without `documents:read`, and 422 for invalid bodies including identity fields. None of these reach retrieval or generation. Identity comes only from the token; query-string and header hints are ignored.
- [x] The LLM and embedding configuration are both checked before any paid embedding call. Context is built as the token's user, and generation receives that exact query, context and user (6.2 ownership checks apply).
- [x] `AssistantQueryResponse`: `status` (`answered`, `insufficient_context` or `no_authorized_context`), `answer`, `request_id`, `sources` and `unverified_source_numbers`. `sources` are metadata from the authoritative context (only when answered, no chunk text); model `[S<n>]` references stay labelled unverified. There is no `citations` field.
- [x] Errors use the existing envelope with fixed messages: 403, 422 (unsafe question), 500 (inconsistent context or unexpected), 502 (embedding or LLM failure, bad output), 503 (not configured or retrieval unavailable), 504 (LLM timeout). A failure is never a 200 answer, and failures are logged as reason code plus request ID.
- [x] `usable_items` is exposed from `generation.py` (a rename), so the API lists exactly the sources placed in the prompt.
- [x] Tests: 24 API tests in `test_assistant_api.py` (real auth and retrieval on `rag_system_test`, fake LLM). The 6.2 endpoint-guard test now expects exactly this one new path. Route mutation checks were each caught: dropped permission, timeout mapped to 502, failure turned into 200, sources listed when not answered.
- [x] Full suite 266/266, 0 skipped. `rag_system` unchanged. Live smoke test on `rag_system` (no LLM call): 401 without token, 503 "embedding provider is not configured" for a valid request, 422 for `user_id` in the body, 405 for GET.

### Part 6.2 — Grounded LLM generation service

- [x] `AnswerGenerator` (`app/services/rag/generation.py`) reuses the existing `LLMProvider`/`create_llm_provider()` (Groq), with no second client or configuration. It takes the validated `RagQuery`, the Part 6.1 `RetrievalContext` and the `AuthenticatedUser`, makes at most one provider call with the configured model, temperature, max tokens and timeout, and passes no tools.
- [x] Grounding prompt: a fixed system message (sources only, no invention, `INSUFFICIENT_CONTEXT` signal, labelled inference, no tools or outside access, final answer only, rules immune to question and sources) and a user message holding the question plus the 6.1 sources inside unforgeable boundaries.
- [x] Prompt-injection defences: retrieved text only in the user message, the system message proven identical to the fixed template, an explicit untrusted-data rule, and questions containing the boundary token refused. These are defences in depth, not a guarantee.
- [x] No context, no call: empty or all-blank context returns a fixed `no_authorized_context` result without a provider call. Missing or malformed context, another user's or question's context, and duplicate ranks raise `invalid_context` without a call.
- [x] Output validation: non-`LLMResponse`, non-text, empty, truncated (`length`), other non-`stop` finish reasons and output echoing the boundary token are rejected. `INSUFFICIENT_CONTEXT` maps to a fixed `insufficient_context` answer.
- [x] `[S<n>]` references are stored as `unverified_source_numbers`; the authoritative context is kept on the result for Part 7.
- [x] `RagGenerationError` has fixed messages and categories and no chained provider exception. Logs hold metadata only.
- [x] Provider: added `LLMProviderTimeoutError(LLMProviderError)` for `openai.APITimeoutError`/`TimeoutError`, so timeouts can be told apart. It is backward compatible; no other provider behaviour changed.
- [x] Tests: 23 generation tests (21 unit with fake providers and the real provider class over a fake client, 2 pipeline tests on the demo dataset in `rag_system_test` showing zero SQL during generation and no unauthorized chunk text in the prompt) and 1 provider timeout test. Mutation checks were each caught: calling the LLM on empty context, sources in the system message, a skipped context-owner check, accepted truncation, and chained provider errors.
- [x] Full suite 242/242, 0 skipped. `rag_system` unchanged (`--verify-only` passes).
- [x] Live check on 2026-10-09 (synthetic contexts, 3 Groq calls, `max_retries=0`, no database): grounded answer correct and cited, `INSUFFICIENT_CONTEXT` returned exactly and mapped, prompt-injection text ignored. All calls finished `stop` with 82–135 completion tokens (52–94 of them reasoning) against the 1,024 limit.
- [x] Live answers over real demo context verified after local embeddings (see "Local embeddings" above). A few samples are not a guarantee of model behaviour.

### Part 6.1 — Query processing + secure context construction

- [x] `RagQuery` (`app/schemas/rag.py`): strict string, whitespace trimmed, empty, whitespace-only and over-2,000-character questions rejected. `top_k` is a strict integer from 1 to `VectorSearchService.MAX_TOP_K` (20), and identity fields are rejected.
- [x] `ContextBuilder` (`app/services/rag/context.py`) takes the `AuthenticatedUser`, refuses users without `documents:read`, and calls the existing `VectorSearchService.search_text` as that user. It has no database session of its own.
- [x] `VectorSearchResult` gains `document_title`, read through a join in the same authorized SQL statement (authorization still in WHERE before ORDER BY/LIMIT). The public `/search/vector` response is unchanged.
- [x] Structured `RetrievalContext`: `status` (`context_ready` or `no_authorized_context`), ranked `ContextItem`s (rank, chunk/document IDs, title, chunk index, page, source locator, verbatim content, distance, similarity), distinct `sources`, counts, and a deterministic `render()`. Source boundaries carry a digest of the context, so document text cannot forge them.
- [x] `RAG_MAX_CONTEXT_CHARACTERS` (32,000): lower-ranked results are dropped whole and counted, never cut.
- [x] Failures propagate (embedding config/provider, vector search, database); only a successful empty retrieval yields `no_authorized_context`. Logs hold counts, user ID and duration only.
- [x] Tests: 11 validation and 22 context tests (12 unit, 10 integration on the demo dataset in `rag_system_test`). Context chunk IDs are proven to be exactly the secure search's results in ranking order, the builder issues exactly one SQL statement (the authorized search), SUPER_ADMIN loses a document when its grant is revoked, and the Procurement injection stays data. Mutation checks (reversed order, an injected extra chunk, removed SQL predicate) are each caught.
- [x] Full suite 218/218, 0 skipped. Live non-destructive regression on `rag_system`: all existing endpoints behave as before; row counts unchanged; `--verify-only` passes.
- [x] Live context on `rag_system` verified once the 45 chunks were embedded locally (see "Local embeddings" above).

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

- Phase 7: validate `unverified_source_numbers` against `GenerationResult.context` before presenting citations.
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
- The Groq keys (old and new) were shared in chat; rotate the current one in the Groq console after the hackathon.
- The model sometimes cites with full-width brackets (`【S1】`), which the `[S<n>]` parser does not recognize, so `unverified_source_numbers` can be empty for an answered reply. Display-only; Part 7 citation work should accept both forms.
- `all-MiniLM-L6-v2` embeds at most 256 word pieces per chunk; text beyond that in a long chunk does not affect retrieval (it still reaches the LLM).
- Demo PDF filenames in `backend/data/documents/` are deterministic and shared by every database. Any ad-hoc `reset_dataset` or `generate_dataset` run against `rag_system_test` must set `DOCUMENT_STORAGE_PATH` to a temporary directory, as the test fixtures do. Otherwise it deletes `rag_system`'s stored PDFs. This happened once on 2026-10-09 (database untouched). The PDFs were restored from the checksummed artifacts in `backend/data/demo/documents/`, and `--verify-only` passes.
- Only the six hackathon demo accounts have passwords in `rag_system`; the other demo users get one only through `scripts/set_demo_passwords.py` with `DEMO_USER_PASSWORD`.
- The optional OpenAI embedding provider is verified only with fake clients (no OpenAI key is configured, or needed).
- Existing non-blocking warnings: PyMuPDF legacy `fitz` deprecation, and asyncpg unclosed-connection/socket warnings from the Part 3 PDF-ingest API test, which uses the global engine across event loops.
- Pre-existing Part 2.2 drift reported by `alembic check`: redundant `UniqueConstraint`s on association tables whose composite primary keys already enforce uniqueness. Not changed in Part 4.
- Live database tests need `DATABASE_URL` (never put it in `backend/.env`). Run them against the test database, because several existing tests delete **all** documents: `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_system_test .venv/bin/python -m unittest discover -s tests`. Running the suite against `rag_system` would delete the demo documents; restore them with `scripts/generate_demo_dataset.py`.

## Next immediate task

Awaiting instruction (Part 6.4 or Part 7 citation validation). Not started; it begins only after explicit approval.

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
