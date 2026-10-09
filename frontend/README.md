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
| `VITE_USE_MOCK_API` | `false` | **Development only.** Simulates the not-yet-built assistant endpoint. Ignored in production builds. |

The backend has no CORS middleware, so the browser always talks to the Vite origin and the proxy forwards `/api`. A production deployment should serve `dist/` and the API from the same origin, for example through a reverse proxy.

Never put secrets in these files: every `VITE_*` value is embedded in the public bundle. The frontend never receives provider keys, the JWT secret or database credentials.

## Routes

| Route | Access | Purpose |
|---|---|---|
| `/login` | public | Sign in (`POST /api/v1/auth/login`) |
| `/app/chat` | signed in | Secure AI assistant |
| `/app/profile` | signed in | Identity, roles and permissions from `GET /api/v1/auth/me` |

Route guards are UX only; every API call is authorized by the server.

## Backend contract

| Endpoint | Used for |
|---|---|
| `POST /api/v1/auth/login` | Get a bearer token (`{access_token, token_type, expires_in}`) |
| `GET /api/v1/auth/me` | Current user (`id, email, full_name, roles, permissions`) |
| `POST /api/v1/assistant/query` | **Provisional.** Generated answers with citations. It does not exist yet (backend Part 6). |
| `POST /api/v1/search/vector` | Fallback while the assistant endpoint is missing: shows the caller's authorized passages (page, similarity, excerpt) |

Wire types live in `src/types/api.ts` and mirror the backend schemas. The assistant request and response types are marked **PROVISIONAL** and must be aligned with the real contract when Part 6 ships.

## Authentication

- Login, then `/auth/me`. The token is kept in `sessionStorage`: it is scoped to the tab, survives reloads and is cleared on sign-out. It is attached only by `src/services/api.ts`.
- A 401 from any authenticated call, or reaching the token's `expires_in`, signs the user out and returns them to `/login` with a "session expired" notice.
- Roles shown in the UI are exactly what `/auth/me` returns. There is no role switcher; switch roles by signing in as another account.

## Hackathon demo accounts

The login page shows six clickable **Hackathon Demo Accounts** from `src/config/demoAccounts.ts`, one active seeded user per role, with SUPER_ADMIN shown as "CEO / Super Admin". Clicking a card only fills the email and password. Logging in still calls the real `POST /api/v1/auth/login`, and the identity shown afterwards comes from `GET /api/v1/auth/me`. These are intentionally public, **local-demo-only** credentials. The backend test suite fails if this file drifts from `backend/demo_dataset/credentials.py`. Set `VITE_SHOW_DEMO_ACCOUNTS=false` to hide them; the build then leaves them out of the bundle.

## Mock mode

Do not use mock mode for a security demo: it simulates server responses in the browser. `VITE_USE_MOCK_API=true npm run dev` replaces **only** the missing assistant endpoint with `src/mocks/mockAssistant.ts`. That file simulates answers, citations and restricted states for the demo questions. The chat header shows a **Mock responses** badge. Login, `/auth/me` and everything else still use the real backend. Production builds compile the mock out entirely; the bundle was checked for this.

## Known limitations

- `/auth/me` returns no department, so only role and email are shown.
- `/search/vector` returns no document titles, so fallback passages are labelled "Authorized source" with page numbers.
- Until the backend has embeddings (an OpenAI key or another embedding provider) and the assistant endpoint (Part 6), real chat requests show "Service temporarily unavailable".
