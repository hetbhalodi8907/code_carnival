# Nexora frontend: Secure AI Workspace

A demo-ready React client for the secure RAG backend. It is a presentation layer only: **the FastAPI backend is the sole authority for identity, roles, permissions and document access.**

Stack: React 19, TypeScript 5.9, Vite 7, Tailwind CSS 4, shadcn/ui-style components (Radix primitives), React Router 7 and Vitest 4. The visual language is described in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).

## Run

Requires Node ≥ 20.19 and the backend running on `http://localhost:8000` with `JWT_SECRET_KEY` set and demo passwords created (see the root README).

From the project root, then open http://localhost:5173:

```bash
cd frontend
npm install
npm run dev
```

Defaults work for local development. To override them, first copy the example file with `cp .env.example .env.local`.

Paste commands without trailing `# comments`: macOS zsh passes them to npm as extra arguments. Vite reads its first argument as the project root, so `npm run dev # note` once served an empty 404, which showed as a blank white page. The `dev` and `preview` scripts now pin the root (`vite .`), so stray arguments are ignored.

| Command | Purpose |
|---|---|
| `npm run dev` | dev server with `/api` proxied to the backend |
| `npm run build` | type-check and production build to `dist/` |
| `npm run preview` | serve `dist/` (also proxies `/api`) |
| `npm run test` | Vitest + Testing Library |
| `npm run lint` / `npm run typecheck` | ESLint / `tsc -b` |

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_BASE_URL` | empty | Backend origin. Leave empty to call the same origin through the Vite proxy. |
| `VITE_DEV_PROXY_TARGET` | `http://localhost:8000` | Where the dev/preview proxy forwards `/api`. |
| `VITE_SHOW_DEMO_ACCOUNTS` | `true` | Show the clickable hackathon demo accounts on the login page. |
| `VITE_USE_MOCK_API` | `false` | **Development only.** Simulates the assistant endpoint. Ignored in production builds. |

The backend has no CORS middleware, so the browser always talks to the Vite origin and the proxy forwards `/api`. A production deployment should serve `dist/` and the API from the same origin, for example through a reverse proxy.

Never put secrets in these files: every `VITE_*` value is embedded in the public bundle. The frontend never receives provider keys, the JWT secret or database credentials.

## Routes

| Route | Access | Purpose |
|---|---|---|
| `/login` | public | Sign in (`POST /api/v1/auth/login`) |
| `/app/dashboard` | signed in | Role-aware dashboard and application home (`GET /api/v1/dashboard/overview`) |
| `/app/chat` | signed in | Secure AI assistant |
| `/app/upload` | signed in; usable with `documents:write` | Upload a PDF (`POST /api/v1/documents/ingest`) |
| `/app/upload-image` | signed in; usable with `documents:write` | Upload a PNG/JPEG for OCR (`POST /api/v1/documents/ingest-image`) |
| `/app/profile` | signed in | Identity, roles and permissions from `GET /api/v1/auth/me` |

Route guards are UX only; every API call is authorized by the server. The Upload links and forms appear only for accounts whose `/auth/me` permissions include `documents:write` (SUPER_ADMIN only in the demo data); the backend enforces the permission on every upload. An uploaded document is readable only by its uploader until further grants are added.

## Backend contract

| Endpoint | Used for |
|---|---|
| `POST /api/v1/auth/login` | Get a bearer token (`{access_token, token_type, expires_in}`) |
| `GET /api/v1/auth/me` | Current user (`id, email, full_name, roles, permissions`) |
| `GET /api/v1/dashboard/overview` | Dashboard: one read-only call, no parameters. Sections the account may not read arrive as `null` and are not rendered; metrics with no stored source arrive in `unavailable` |
| `POST /api/v1/assistant/query` | Chat: sends `{query, top_k: 5}` (the backend `RagQuery`) with the bearer token; returns `{status, answer, request_id, sources, unverified_source_numbers}` |
| `POST /api/v1/documents/ingest` | PDF upload: multipart field `file`, up to 25 MB. Stores, chunks and embeds in one request; `embedding_status` (`completed`, `failed`, `not_configured`) and `embedding_model` say whether it is searchable |
| `POST /api/v1/documents/ingest-image` | Image upload: multipart field `file`, PNG or JPEG up to 10 MB. Runs OCR, then stores, chunks and embeds in one request; returns `ocr_line_count`, `ocr_mean_confidence` and `embedding_status` (no `embedding_model`) |
| `POST /api/v1/embeddings/documents/{document_id}` | Retry indexing for an already stored document (never re-uploads). Used only when `embedding_status` was not `completed` |

The dashboard (`src/pages/DashboardPage.tsx`, `src/components/dashboard/`) renders only what the server sent, with loading skeletons, a retry on failure, refresh that keeps the last data, and empty states. Charts are plain HTML/CSS (no chart library); every figure is also printed as text. Wire types: `src/types/dashboard.ts`.

Wire types live in `src/types/api.ts` and mirror the backend schemas (`backend/app/schemas/rag.py`). `src/services/assistant.ts` accepts only that contract: a body that does not match it is shown as an error, never as an answer.

### Chat states

| `status` | Shown as |
|---|---|
| `answered` | The answer, then **Sources retrieved for this answer**: document title, page and similarity (a plain cosine score, not a confidence percentage) for each authorized passage the model was given. The API returns no passage text. |
| `insufficient_context` | "Not enough information" with the server's message |
| `no_authorized_context` | "No authorized information found" with the server's message; no document is named |
| `access_denied` | **Access Denied**: "You don't have permission to access the information requested." plus "Contact your administrator if you believe you should have access." Fixed copy only; a denial that arrives with sources is rejected as malformed and shown as an error |

Sources are what the server retrieved, not verified citations. The model's `[S<n>]` markers stay plain text in the answer, are not linked to any source, and are listed beneath it as unverified. Citation validation is backend Part 7.

Errors show fixed, friendly copy and never server detail:

| HTTP | Shown as |
|---|---|
| 401 | Signs out and returns to `/login` with a "session expired" notice |
| 403 / 422 | "Access restricted" / "Question not accepted" (no retry) |
| network, 500, 502, 503, 504 | A specific message plus **Retry**, which re-asks the same question in place |

One request runs at a time. Retry reuses the failed reply instead of adding new messages. The old fallback to `POST /api/v1/search/vector` has been removed: an assistant failure is reported, never replaced by plain search results that lack its grounding.

## Authentication

- Login, then `/auth/me`. The token is kept in `sessionStorage`: it is scoped to the tab, survives reloads and is cleared on sign-out. It is attached only by `src/services/api.ts`.
- A 401 from any authenticated call, or reaching the token's `expires_in`, signs the user out and returns them to `/login` with a "session expired" notice.
- Roles shown in the UI are exactly what `/auth/me` returns. There is no role switcher; switch roles by signing in as another account.

## Hackathon demo accounts

The login page shows six clickable **Hackathon Demo Accounts** from `src/config/demoAccounts.ts`, one active seeded user per role, with SUPER_ADMIN shown as "CEO / Super Admin". The cards show each role, its description and its email; clicking one fills the email and password (the password is not displayed on the card). Logging in still calls the real `POST /api/v1/auth/login`, and the identity shown afterwards comes from `GET /api/v1/auth/me`. These are intentionally public, **local-demo-only** credentials. The backend test suite fails if this file drifts from `backend/demo_dataset/credentials.py`. Set `VITE_SHOW_DEMO_ACCOUNTS=false` to hide them; the build then leaves them out of the bundle.

## Mock mode

Do not use mock mode for a security demo: it simulates server responses in the browser. `VITE_USE_MOCK_API=true npm run dev` replaces **only** the assistant endpoint with `src/mocks/mockAssistant.ts`, for previewing the chat without a backend that has embeddings. That file simulates the three statuses for the demo questions. The chat header shows a **Mock responses** badge. Login, `/auth/me` and everything else still use the real backend. Production builds compile the mock out entirely; the bundle was checked for this.

## Known limitations

- `/auth/me` returns no department, so only role and email are shown.
- The backend embeds locally (no OpenAI key). If its chunks are not embedded yet, or its model is unavailable, chat requests fail with 502/503 and show a retryable error.
- Sources are not yet verified citations (backend Part 7).
