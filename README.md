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

Embedding generation and vector search need `OPENAI_API_KEY`. Without it, those endpoints return HTTP 503.

## Frontend (demo-ready)

`frontend/` contains the React + TypeScript + Tailwind + shadcn/ui client: login, a protected app shell with the signed-in user's role, the secure AI chat with citation and access-restricted states, a profile page, and dark/light themes. It consumes only the existing backend APIs and makes no access decisions. Run it with `cd frontend && npm install && npm run dev` (it proxies `/api` to `localhost:8000`). See [frontend/README.md](frontend/README.md) and [frontend/DESIGN_SYSTEM.md](frontend/DESIGN_SYSTEM.md).

## LLM provider (Groq)

Answer generation will use Groq through its OpenAI-compatible API (the existing `openai` SDK; no extra dependency). Put `GROQ_API_KEY` in the git-ignored `backend/.env` (see `.env.example`). The default model is `openai/gpt-oss-120b`; override it with `LLM_MODEL`. Check connectivity with one small API call:

```bash
.venv/bin/python scripts/check_llm_provider.py
```

Only the provider layer exists (`app/services/llm/`). Nothing calls it yet; the RAG pipeline and endpoint are Part 6. **Groq offers no embedding models**, so vector search still needs `OPENAI_API_KEY` (or another embedding provider) before it can return results.

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

**Retrieval needs embeddings.** Groq has no embeddings API, and the demo chunks are only embedded once an embedding provider is configured. Until then, questions return "Service temporarily unavailable"; logins, roles and permissions work regardless. With an OpenAI key in `backend/.env` (`OPENAI_API_KEY=...`), run `.venv/bin/python scripts/generate_demo_dataset.py --with-embeddings` once (about 9,000 tokens). Answers appear as **authorized passages**, because LLM answer generation is Part 6.

### Demo script

1. **Finance Manager:** click the card, then **Log in as Finance Manager**. Point out the sidebar: name, email, role, *Authenticated*, permissions from the server.
2. Ask *"What is the Finance department budget?"*: the Finance Report passage (INR 1.5 crore) is returned.
3. Ask *"What are the confidential HR salary bands and the HR escalation process?"*: every passage is labelled `CONFIDENTIAL FINANCE` or `INTERNAL`, and nothing comes from the HR policy, because the server filters it inside the SQL query. **Log out.**
4. **Employee (Kabir Sethi):** ask *"What is my compensation statement and revised annual CTC?"*: his own statement is returned (INR 11.4 lakh).
5. Ask *"What is Rahul Gupta's compensation statement and revised annual CTC?"*: only `PUBLIC`/`INTERNAL` passages or his own statement come back, never Rahul's. **Log out.**
6. **HR Manager:** ask *"What are the HR salary bands?"*: `CONFIDENTIAL HR` passages are returned. **Log out.**
7. Optional: **CEO / Super Admin** sees both Finance and HR, through explicit grants on each document, not a bypass.

## Important scope boundary

This repository contains documentation, project control, the FastAPI backend foundation, the database schema, PDF ingestion, pgvector embeddings, a synthetic (fictional) demo dataset, authentication, RBAC, document authorization and authorization-aware vector retrieval. It intentionally does not contain real company data, RAG, LLM calls, citations, OCR, an advanced frontend (beyond the basic demo client), or later-phase implementation.
