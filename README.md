# Secure Multi-Modal RAG System

A college project for building a retrieval-augmented generation system that combines PDF documents, OCR-extracted images, and structured database records. The system will enforce document-level and row-level authorization before any retrieved content reaches an LLM.

## Project goal

The application will let an authenticated user ask natural-language questions over a controlled collection of academic or organizational knowledge. It will retrieve only content the user is authorized to access, ground the answer in those exact sources, and expose a citation for every factual claim.

## Security boundary

> Unauthorized documents, chunks, and database rows must never be retrieved into the LLM context. Retrieval and authorization must be enforced together in the backend; the frontend cannot be relied upon for access control.

## Planned capabilities

- Ingest PDF files and normalize extracted text.
- Ingest structured records and preserve source metadata.
- Extract text from images with OCR.
- Chunk and embed mixed content into a PostgreSQL pgvector index.
- Enforce role, document, and row-level permissions during retrieval.
- Generate answers through a configurable LLM provider.
- Require exact source citations for factual claims.
- Validate that cited sources were authorized and actually used.
- Provide a React and TypeScript assistant interface built with Tailwind CSS and shadcn/ui.

## Current status

Phase 0 project initialization and documentation are complete. Parts 1.1–1.10 completed the minimal FastAPI foundation, centralized environment settings, logging, request tracing, structured errors, health/readiness endpoints, testing, cleanup, hardening, and final verification.

Part 2.1 is implemented and verified. PostgreSQL 15.17 is running locally, the `postgres` role and `rag_system` database were created without application data, SQLAlchemy async connectivity passed `SELECT 1`, and Alembic successfully applied and re-ran the initial migration. Part 2.2 is also implemented and verified: the `623078a250c3` Alembic revision creates all 10 ORM tables with foreign keys, primary keys, unique constraints, and indexes; live PostgreSQL inspection and duplicate-assignment tests pass; the migration was downgraded to `0001`, re-applied, and confirmed as head. Part 3 (PDF ingestion) is complete: validation, page-wise extraction and cleaning, deterministic chunking with metadata, and transactional document/chunk persistence (`POST /api/v1/documents/preview`, `POST /api/v1/documents/ingest`).

Part 4 (pgvector + embeddings + vector search) is complete. Chunks carry an `embedding vector(1536)` and an `embedding_model` column (migration `466650ac5b92`). An OpenAI embedding provider (`text-embedding-3-small`, configured through `EMBEDDING_*` and `OPENAI_API_KEY`) generates embeddings via `POST /api/v1/embeddings/documents/{document_id}`. `POST /api/v1/search/vector` returns the top-K chunks by cosine distance. All 98 backend tests pass.

A deterministic **synthetic demo dataset** for the fictional company Nexora Technologies is complete. It has 5 departments, 6 roles, 11 permissions, 20 users, 10 multi-page PDFs ingested through the existing pipeline, explicit role and user document grants, and 23 security test scenarios. See [backend/data/demo/README.md](backend/data/demo/README.md). Its roles, permissions and grants are what Part 5 enforces.

Part 5 (authentication, RBAC, document authorization and retrieval-level security) is complete. Users sign in with email and password (Argon2id hashes) and receive a short-lived JWT. Permissions come from the database. **Vector search applies document authorization inside the SQL query, before ranking and `LIMIT`**, so unauthorized chunks never reach the application. The full backend suite (168 tests) passes against the `rag_system_test` database.

Part 6.1 (query processing and secure context construction) is complete. A validated question goes to the existing authorization-aware vector search as the authenticated user. Only the authorized results become structured context items, kept in ranking order with their source metadata. The full backend suite (218 tests) passed against `rag_system_test`.

Part 6.2 (grounded LLM generation) is complete as an internal service. Using the existing Groq provider, it answers only from the Part 6.1 context, never calls the model without usable context, and validates the model's output. Citations remain unverified until Part 7. The full backend suite (242 tests) passed against `rag_system_test`.

Part 6.3 (authenticated assistant query API) is complete: `POST /api/v1/assistant/query` chains the authenticated user, Part 6.1 context and Part 6.2 generation. The full backend suite (266 tests) passes against `rag_system_test`.

## Documentation map

- [Project requirements](docs/PROJECT_REQUIREMENTS.md)
- [System architecture](docs/SYSTEM_ARCHITECTURE.md)
- [Technology stack](docs/TECH_STACK.md)
- [Data flow](docs/DATA_FLOW.md)
- [Security model](docs/SECURITY_MODEL.md)
- [API specification](docs/API_SPECIFICATION.md)
- [Database schema](docs/DATABASE_SCHEMA.md)
- [RAG design](docs/RAG_DESIGN.md)
- [Development plan](docs/DEVELOPMENT_PLAN.md)
- [Progress tracker](progress/PROGRESS.md)
- [Architecture decisions](progress/DECISIONS.md)
- [Actionable TODOs](progress/TODO.md)

## Local development expectations

The full application will be developed with Docker Compose for PostgreSQL and the backend, with environment variables controlling configuration and secrets. Detailed setup commands will be added only after Phase 1 begins.

## FastAPI backend

The FastAPI application is located in `backend/app/main.py`. Its environment settings are centralized in `backend/app/core/config.py`.

Start it from the repository root with:

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload
```

Copy `backend/.env.example` to `backend/.env` when local overrides are needed. The root endpoint is available at `http://127.0.0.1:8000/`. Swagger/OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

The database needs the pgvector extension (`pgvector/pgvector` image in `docker-compose.yml`, or `brew install pgvector` locally). From `backend/`, apply migrations and, optionally, seed the synthetic demo dataset (the last command):

```bash
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_system
.venv/bin/alembic upgrade head
.venv/bin/python scripts/generate_demo_dataset.py
```

Run the tests against a separate database, because some tests delete all documents:

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_system_test \
  .venv/bin/python -m unittest discover -s tests
```

> Shell blocks in these docs contain no `# comments`: macOS zsh does not treat `#` as a comment when you paste at the prompt, so a trailing note is passed to the command as extra arguments.

Embeddings are generated locally (see [Local embeddings](#local-embeddings)); no API key is needed.

## Local embeddings

Document and query embeddings use the local `sentence-transformers/all-MiniLM-L6-v2` model (384 dimensions, CPU, L2-normalized) through `SentenceTransformerEmbeddingProvider` in `app/services/embeddings/provider.py`. No OpenAI key is required. The model downloads once (about 90 MB) to `~/.cache/huggingface`, then works offline (`HF_HUB_OFFLINE=1`). Documents and queries always use the same configured model: retrieval filters on `embedding_model`, and migration `a1d4c7e9f3b2` resized the column to `vector(384)`, clearing any vectors from the previous 1536-dimension model.

Settings (defaults shown): `EMBEDDING_PROVIDER=sentence-transformers`, `EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2`, `EMBEDDING_DIMENSION=384`. `EMBEDDING_PROVIDER=openai` remains available with `OPENAI_API_KEY` and a `text-embedding-3` model requested at 384 dimensions. The model reads at most 256 word pieces per chunk, so text beyond that in a long chunk does not affect its embedding (it still reaches the LLM as context).

From `backend/`, migrate and then embed the demo chunks. The embedding step is idempotent: a rerun skips chunks already embedded with the configured model.

```bash
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_system
.venv/bin/alembic upgrade head
.venv/bin/python scripts/generate_demo_dataset.py --with-embeddings
```

## Frontend (demo-ready)

`frontend/` contains the React + TypeScript + Tailwind + shadcn/ui client: login, a protected app shell with the signed-in user's role, the secure AI chat (grounded answers with the sources retrieved for them, insufficient-context and no-authorized-context states, and safe errors), a profile page, and dark/light themes. It consumes only the existing backend APIs and makes no access decisions. Run it with `cd frontend && npm install && npm run dev` (it proxies `/api` to `localhost:8000`). See [frontend/README.md](frontend/README.md) and [frontend/DESIGN_SYSTEM.md](frontend/DESIGN_SYSTEM.md).

## Role-aware dashboard

After signing in, every account lands on `/app/dashboard` (the Assistant and the two upload pages are unchanged). The page is built from one read-only call, `GET /api/v1/dashboard/overview`, computed by the backend with database-side aggregation. It uses no LLM, so it works when Groq or LM Studio is down. The response carries no role or scope parameter: the user, roles and permissions come from the verified token and the database, and a section the account may not read is `null` (the server never sends it).

| Account | Sections it receives |
|---|---|
| CEO / Super Admin | Organization projects (status, milestones, blockers, workload), finance, workforce, access control, readable documents |
| Finance Manager (`finance:read`) | Budget vs actual, remaining budget, utilization, monthly trend, spend by category and project, recent expenses, pending approvals |
| HR Manager (`hr:read`) | Active headcount, departments, roles, a compensation record COUNT (never amounts), HR documents they may read |
| Engineering Manager (`engineering:read`) | Engineering projects plus any they lead or belong to: status, milestones, blockers, overdue, workload |
| Security Manager (`security:read`) | Roles and permissions, document grant counts, indexing status |
| Employee | Only projects they lead or are recorded on, with their role and upcoming milestones |

Everyone also gets counts for the documents they are **granted** (the same `document_access_condition` as retrieval) and a "Not available" list for metrics with no stored source. Amounts stay in their own currency and are never added across currencies. Real zero values are shown as 0; a missing budget or percentage is shown as "Not available".

**Data sources and limits.** Projects, departments, users, roles, permissions, document grants, documents and chunks are the existing records. Budgets, expenses, project members and milestones are **fictional Nexora demo data** in four additive tables (migration `c3f6e9b2d5a4`, seeded by `backend/scripts/seed_dashboard_data.py`); the page is labelled "Demo dataset". Not stored, so not shown: authentication failures, denied requests or other security events (server logs only), recent activity beyond newly added documents, real-time system health, hire dates or workforce history, and personal tasks.

**Setup** (from `backend/`; both steps are additive and safe to rerun; check the printed database name first):

```bash
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_system
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed_dashboard_data.py   # needs the demo dataset and seed_structured_data.py first
```

## LLM provider (Groq)

Answer generation will use Groq through its OpenAI-compatible API (the existing `openai` SDK; no extra dependency). Put `GROQ_API_KEY` in the git-ignored `backend/.env` (see `.env.example`). The default model is `openai/gpt-oss-120b`; override it with `LLM_MODEL`. Check connectivity with one small API call:

```bash
.venv/bin/python scripts/check_llm_provider.py
```

The provider layer is `app/services/llm/`. Its only caller is the Part 6.2 generation service below, which `POST /api/v1/assistant/query` exposes. **Groq offers no embedding models**, so embeddings come from the local model (see [Local embeddings](#local-embeddings)).

## Secure RAG context (Part 6.1)

`app/services/rag/context.py` turns a question into structured, authorized context for answer generation. It is an internal service; there is no new HTTP endpoint.

1. **Validate** with `RagQuery` (`app/schemas/rag.py`). Surrounding whitespace is trimmed, and empty, whitespace-only and over-2,000-character questions are rejected. `top_k` is a strict integer from 1 to 20, the same bounds as vector search. Unknown fields such as `user_id` or `role` are rejected.
2. **Authorize.** The caller passes the `AuthenticatedUser` from the JWT dependency, and users without `documents:read` are refused before any retrieval.
3. **Retrieve** through the existing `VectorSearchService` as that user. Authorization stays inside its SQL, before `ORDER BY`/`LIMIT`. The builder has no database session of its own, so it cannot run another query or filter results in Python. Document titles come from the same SQL statement.
4. **Build** one `ContextItem` per authorized result, in ranking order. Each item carries the rank, chunk ID, document ID and title, chunk index, page number, source locator, verbatim content, and distance and similarity. Storage paths, credentials and access-control data are never included. `render()` wraps each source in BEGIN/END lines that carry a digest of the whole context, so document text cannot fake a source boundary.

Zero authorized results give `status="no_authorized_context"` with no items or sources. Embedding-provider and database failures raise errors; they never turn into an empty context. `RAG_MAX_CONTEXT_CHARACTERS` (default 32,000) caps the total chunk text. Lower-ranked results beyond it are dropped whole and counted, never cut mid-chunk. Retrieved text, including the deliberate prompt-injection comment in `Procurement_Report.pdf`, is treated as data. Logs record counts, the user ID and the duration, never the question or the content.

On `rag_system` all 45 demo chunks are embedded with the local model, so live context works without any API key. Tests use the offline lexical embedding provider on `rag_system_test`.

## Grounded generation (Part 6.2)

`app/services/rag/generation.py` turns a `RagQuery` and its Part 6.1 `RetrievalContext` into an answer through the existing Groq provider (`create_answer_generator()` wraps `create_llm_provider()`). `POST /api/v1/assistant/query` (Part 6.3, below) is its only HTTP entry point.

```
RagQuery + RetrievalContext + AuthenticatedUser
  -> check the context belongs to this user and question
  -> no usable context? return the fixed "no_authorized_context" answer (no LLM call)
  -> two messages: system (fixed rules) + user (question + delimited sources)
  -> one provider call (configured model, temperature, max tokens, timeout; no tools)
  -> validate the output -> GenerationResult
```

- **Grounding.** The system message holds only fixed rules:
  - answer only from the sources, and never invent facts, figures, names, pages or sources;
  - say what the sources do not cover, and label any inference;
  - claim no other access, use no tools, and give the final answer without reasoning.

  If nothing in the sources answers the question, the model replies `INSUFFICIENT_CONTEXT`. The service turns that into a fixed `insufficient_context` answer.
- **Prompt injection.** Retrieved text goes only into the user message, inside the Part 6.1 source boundaries that document text cannot forge. The system message says sources are untrusted data and never instructions. A question that contains the boundary token is refused before any call. This reduces prompt-injection risk; it cannot rule it out.
- **No context, no call.** An empty context, or one whose chunks are all blank, returns the fixed `no_authorized_context` answer without contacting the provider. A missing or malformed context, a context built for another user or question, or duplicate source numbers raise an `invalid_context` error, again without a call.
- **Output validation.** The model's output is rejected (`RagGenerationError`) when it is not an `LLMResponse`, is empty, was cut off (`finish_reason="length"`), ended for any reason other than `stop`, or reproduces the source-boundary token. Provider failures become `provider_error` or `provider_timeout`. Errors carry fixed messages and no chained provider exception.
- **Citations are unverified.** The model is asked to cite `[S<n>]` source numbers. `GenerationResult.unverified_source_numbers` records them as proposals only, and `GenerationResult.context` keeps the authoritative chunks for Part 7 citation validation.
- **Data access and logs.** The generator runs no database query, search or file read; tests confirm it issues zero SQL statements. Logs hold status, user ID, model, token counts and duration, never the question, sources, prompt or answer.

Configuration: `GROQ_API_KEY` in the git-ignored `backend/.env`; `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_OUTPUT_TOKENS` and `LLM_TIMEOUT_SECONDS` are reused unchanged. Live answers use the locally embedded Part 6.1 context. The generation tests use fake providers and never call Groq. Run them from `backend/`:

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_system_test \
  .venv/bin/python -m unittest discover -s tests -p "test_rag_generation.py"
```

## Assistant query API (Part 6.3)

`POST /api/v1/assistant/query` answers a question from documents the caller may read. It needs a bearer token (`Authorization: Bearer <token>` from `POST /api/v1/auth/login`) and the `documents:read` permission.

Request (the `RagQuery` schema): `query` is 1–2,000 characters after trimming, and `top_k` is a strict integer from 1 to 20 (default 5). Any other field, such as `user_id`, `role`, `permissions` or `department`, is rejected with 422.

```json
{"query": "What is the Finance department budget?", "top_k": 5}
```

Response (`AssistantQueryResponse`):

```json
{
  "status": "answered",
  "answer": "The Finance department budget for FY 2025-26 is INR 1.5 crore [S1].",
  "request_id": "6f1c…",
  "sources": [
    {"source_number": 1, "document_id": "…", "document_title": "Nexora Finance Report FY 2025-26",
     "chunk_id": "…", "page_number": 2, "source_locator": "page:2", "similarity": 0.82}
  ],
  "unverified_source_numbers": [1]
}
```

| `status` | Meaning | LLM called |
|---|---|---|
| `answered` | Grounded answer; `sources` lists the authorized passages the model was given | yes |
| `insufficient_context` | The authorized passages do not answer the question; fixed message, no sources | yes |
| `no_authorized_context` | No usable authorized passage; fixed message, no sources | **no** |
| `access_denied` | The question targets information the user may not read. Fixed message ("You don't have permission to access the information requested."), no sources, no document details | yes (it replaces a non-answer; the model only ever saw authorized context) |

`access_denied` is decided only by the server, and only after the model could not answer (`insufficient_context` or `no_authorized_context`), by an isolated check in `app/services/rag/access_denial.py`: (1) a deterministic policy rule for confidential compensation (a named person's, or your own without `employee:self_read`), and (2) a relevance probe, one SQL aggregate over documents the user may NOT read that returns a single similarity number (no text, ids or titles). Denial needs that similarity to reach `ACCESS_DENIAL_MIN_SIMILARITY` and to beat the best authorized similarity by `ACCESS_DENIAL_MARGIN`. Any probe error leaves the ordinary `insufficient_context` answer. The model is never asked to decide access and never sees restricted text. Limitation: the status reveals that restricted material relevant to the question exists; the thresholds are calibrated on the synthetic demo documents with the default local embedding model.

How a request flows:
1. FastAPI checks the token, the account's active status and `documents:read` before the route runs. Missing or invalid tokens get 401, a missing permission gets 403, and an invalid body gets 422; none of these reach retrieval or generation.
2. The route checks that the language model and embedding provider are configured, before any paid embedding call.
3. `ContextBuilder` retrieves as the token's user, with authorization in SQL before ranking and `LIMIT`.
4. `AnswerGenerator` receives that query, context and user, and enforces its ownership and consistency checks.

The user always comes from the token: identity fields in the body, query string or headers are rejected or ignored.

`sources` come from the server's retrieved context, never from the model's answer, and contain metadata only (no chunk text). They are the evidence the model was given, **not validated citations**. `unverified_source_numbers` are the model's own `[S<n>]` references, which may be wrong or point at no source. Citation validation is Part 7.

Errors use the standard `{"error": {"code", "message", "request_id"}}` envelope with fixed messages. They never include provider text, prompts, retrieved text or stack traces.

| Status | Cause |
|---|---|
| 401 / 403 | Missing, invalid or expired token, or an inactive account / no `documents:read` |
| 422 | Invalid body, or a question that cannot be processed safely |
| 500 | Inconsistent retrieval context, or an unexpected error |
| 502 | Embedding provider failed; the LLM failed or returned an empty, incomplete or invalid answer |
| 503 | Embedding provider or LLM not configured; vector search unavailable |
| 504 | LLM timeout |

On the demo database the endpoint answers live: local embeddings for retrieval, Groq for generation. Run the API tests from `backend/` (fake LLM, offline embeddings, test database):

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_system_test \
  .venv/bin/python -m unittest discover -s tests -p "test_assistant_api.py"
```

## Authentication and authorization

**Configuration.** Set `JWT_SECRET_KEY` to a random value of at least 32 characters (`python -c "import secrets; print(secrets.token_urlsafe(48))"`). `JWT_ALGORITHM` defaults to `HS256`, and `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` to `30`. Without a secret, login and protected endpoints return 503, and with `APP_ENV=production` the application refuses to start. Shorter secrets are always rejected.

**Demo sign-in (development only).** Use the six [Hackathon Demo Accounts](#hackathon-demo-accounts) below. Only Argon2id hashes are stored, the script touches demo users only, and it refuses to run in production. Set the six fixed demo logins:

```bash
.venv/bin/python scripts/set_demo_passwords.py --hackathon-accounts
```

Alternatively, give all 20 demo users one password of your choice (`--clear` removes all demo passwords), then try it:

```bash
export DEMO_USER_PASSWORD='<at least 12 characters>'
.venv/bin/python scripts/set_demo_passwords.py
curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email": "vikram.nair@nexora.example", "password": "<DEMO_USER_PASSWORD>"}'
```

The inactive demo user (`farhan.qureshi@nexora.example`) can never sign in. Send the returned token as `Authorization: Bearer <token>`; Swagger's **Authorize** button accepts it.

| Endpoint | Access |
|---|---|
| `GET /`, `/api/v1/health`, `/api/v1/ready`, `/docs` | public |
| `POST /api/v1/auth/login` | public; returns `{access_token, token_type, expires_in}` |
| `GET /api/v1/auth/me` | authenticated; identity, roles and permissions from the database |
| `POST /api/v1/search/vector` | `documents:read`; results limited to the caller's authorized documents |
| `POST /api/v1/assistant/query` | `documents:read`; answers only from the caller's authorized documents |
| `POST /api/v1/documents/preview`, `POST /api/v1/documents/ingest` | `documents:write` (SUPER_ADMIN in the demo dataset); the uploader receives an explicit grant to the new document |
| `POST /api/v1/embeddings/documents/{id}` | `documents:write` **and** access to that document; otherwise 404, the same as a missing document |

Missing, malformed, tampered or expired tokens, and tokens of deactivated users, get **401** with `WWW-Authenticate: Bearer`. Missing permissions get **403**. Invalid credentials and inactive accounts get the same **401** "Invalid email or password."

**Authorization model (default deny).** Roles and permissions come only from `user_roles` → `role_permissions`. A user can access a document only through an explicit `document_role_access` row for one of their roles, or a `document_user_access` row for them personally. Department, classification, filename and ownership never grant access, and SUPER_ADMIN has no bypass. It reaches documents through the same grants. One SQL predicate (`app/services/authorization.py`) defines access and is used both by document checks and by vector retrieval. Identity comes only from the validated token, and request fields such as `user_id` or `role` are rejected or ignored.

## Hackathon Demo Accounts

> **LOCAL / HACKATHON DEMO USE ONLY.** These are intentionally public credentials for fictional, seeded demo users. They are not production credentials. Never run them against a real deployment; the setup script refuses `APP_ENV=production`.

Each account is a real, **active** seeded user holding exactly one role. Passwords are stored only as Argon2id hashes, and every login goes through `POST /api/v1/auth/login`. The login page shows these accounts as clickable cards that only fill the form (set `VITE_SHOW_DEMO_ACCOUNTS=false` to hide them).

| Role (backend) | Shown as | Email | Password | Demonstrates |
|---|---|---|---|---|
| `SUPER_ADMIN` | CEO / Super Admin | `ishaan.malhotra@nexora.example` | `DemoCEO@2026` | Broad access, granted only through explicit document grants (no hidden bypass) |
| `HR_MANAGER` | HR Manager | `meera.iyer@nexora.example` | `DemoHR@2026` | HR policy and compensation statements; Finance reports are not retrieved |
| `FINANCE_MANAGER` | Finance Manager | `vikram.nair@nexora.example` | `DemoFinance@2026` | Finance and procurement reports; the confidential HR policy is not retrieved |
| `ENGINEERING_MANAGER` | Engineering Manager | `ananya.rao@nexora.example` | `DemoEngineering@2026` | Engineering guidelines and IT access policy; the Security policy is not retrieved |
| `SECURITY_MANAGER` | Security Manager | `devika.krishnan@nexora.example` | `DemoSecurity@2026` | Security and IT access-control policies; HR and Finance are not retrieved |
| `EMPLOYEE` | Employee | `kabir.sethi@nexora.example` | `DemoEmployee@2026` | Company-wide documents plus his own compensation statement; a colleague's is not retrieved |

`farhan.qureshi@nexora.example` is deliberately inactive and is never a demo account: the server refuses it with the same message as a wrong password.

### Run the demo

**Terminal 1, backend**, from the project root. `backend/.env` provides `JWT_SECRET_KEY`; never put `DATABASE_URL` there. The password command only needs to run once and is safe to repeat.

```bash
cd backend
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_system
.venv/bin/python scripts/set_demo_passwords.py --hackathon-accounts
.venv/bin/uvicorn app.main:app --port 8000
```

**Terminal 2, frontend**, from the project root (a new terminal). Then open http://localhost:5173.

```bash
cd frontend
npm install
npm run dev
```

**Requirements.** `GROQ_API_KEY` in `backend/.env`, and the demo chunks embedded locally once (`alembic upgrade head`, then `scripts/generate_demo_dataset.py --with-embeddings`; see [Local embeddings](#local-embeddings)). No OpenAI key is needed. Each question gets an answer generated by Groq from the authorized passages only, shown with the sources retrieved for it. Those sources are not yet verified citations (Part 7).

### Demo script

1. **Finance Manager:** click the card, then **Log in as Finance Manager**. Point out the sidebar: name, email, role, *Authenticated*, permissions from the server.
2. Ask *"What is the Finance department budget?"*: the answer gives INR 1.5 crore, and **Sources retrieved for this answer** lists the Finance Report.
3. Ask *"What are the confidential HR salary bands and the HR escalation process?"*: the HR Policy never appears in the answer or its sources, because the server filters it inside the SQL query. Expect "Not enough information", or an answer drawn only from documents this role can read. **Log out.**
4. **Employee (Kabir Sethi):** ask *"What is my compensation statement and revised annual CTC?"*: the answer comes from his own statement (INR 11.4 lakh).
5. Ask *"What is Rahul Gupta's compensation statement and revised annual CTC?"*: Rahul's statement is never a source; expect "Not enough information" or an answer from Kabir's own documents. **Log out.**
6. **HR Manager:** ask *"What are the HR salary bands?"*: the answer comes from the HR Policy, which is listed as a source. **Log out.**
7. Optional: **CEO / Super Admin** sees both Finance and HR, through explicit grants on each document, not a bypass.

## Important scope boundary

This repository contains documentation, project control, the FastAPI backend foundation, the database schema, PDF ingestion, pgvector embeddings, a synthetic (fictional) demo dataset, authentication, RBAC, document authorization, authorization-aware vector retrieval, secure RAG context construction, grounded generation and the authenticated assistant query API. It intentionally does not contain real company data, citation validation, OCR, an advanced frontend (beyond the basic demo client), or later-phase implementation.
