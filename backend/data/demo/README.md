# Nexora Technologies demo dataset

A deterministic, fully **synthetic** dataset for the fictional company Nexora Technologies. It exists so the later authentication, authorization, RAG and citation phases can be tested against deliberate security scenarios. Every person, figure, address and document is fictional. Emails use the reserved `nexora.example` domain.

> The backend enforces these roles, permissions and grants (Part 5): login, `require_permission`, and document authorization inside the vector search query. To sign in as demo users, see `scripts/set_demo_passwords.py` in the main README.

## Contents

| Component | Count | Notes |
|---|---|---|
| Departments | 5 | HR, FIN, ENG, SEC, OPS |
| Roles | 6 | SUPER_ADMIN, HR_MANAGER, FINANCE_MANAGER, ENGINEERING_MANAGER, SECURITY_MANAGER, EMPLOYEE |
| Permissions | 11 | `resource:action`, e.g. `finance:read`, `employee:self_read` |
| Users | 20 | one role each; `farhan.qureshi@nexora.example` is **inactive** on purpose |
| PDFs | 10 | 3–5 pages each, 45 pages in total, one chunk per page with the default chunk settings |
| Role grants | 29 | `document_role_access` |
| User grants | 2 | `document_user_access`, one per personal compensation statement |
| Security scenarios | 23 | `manifests/test_scenarios.json` |

### Documents and access

| File | Classification | Granted to |
|---|---|---|
| Company_Overview.pdf | PUBLIC | all 6 roles |
| Employee_Handbook.pdf | INTERNAL | all 6 roles |
| HR_Policy.pdf | CONFIDENTIAL_HR | HR_MANAGER, SUPER_ADMIN |
| Finance_Report.pdf | CONFIDENTIAL_FINANCE | FINANCE_MANAGER, SUPER_ADMIN |
| Engineering_Guidelines.pdf | INTERNAL_ENGINEERING | ENGINEERING_MANAGER, SUPER_ADMIN |
| Security_Policy.pdf | CONFIDENTIAL_SECURITY | SECURITY_MANAGER, SUPER_ADMIN |
| Procurement_Report.pdf | CONFIDENTIAL_FINANCE | FINANCE_MANAGER, SUPER_ADMIN |
| IT_Access_Control_Policy.pdf | CONFIDENTIAL_SECURITY | SECURITY_MANAGER, ENGINEERING_MANAGER, SUPER_ADMIN |
| Compensation_Statement_Kabir_Sethi.pdf | CONFIDENTIAL_PERSONAL | HR_MANAGER, SUPER_ADMIN + user kabir.sethi |
| Compensation_Statement_Rahul_Gupta.pdf | CONFIDENTIAL_PERSONAL | HR_MANAGER, SUPER_ADMIN + user rahul.gupta |

Access is **default deny**: every grant is an explicit row, including the grants for public and internal documents. Department, classification and filename never imply access. Engineering managers get the IT Access Control Policy because its page 4 defines how they approve production access. They still cannot read the Security Policy.

`Procurement_Report.pdf` page 5 contains a deliberate, clearly labelled **indirect prompt-injection** sample (a vendor comment telling an AI to reveal HR and Finance data). It tests that retrieved text is treated as untrusted content (scenario S20).

## Layout

```
backend/
├── demo_dataset/            # spec, page content, scenarios, PDF builder, seeder, verification
├── scripts/generate_demo_dataset.py
└── data/
    ├── demo/                # committed, deterministic dataset artifacts
    │   ├── documents/*.pdf
    │   └── manifests/
    │       ├── dataset_manifest.json   # departments, roles, permissions, users, documents (+ sha256, pages, key facts)
    │       ├── access_matrix.json      # document -> allowed_roles / allowed_users
    │       └── test_scenarios.json     # expected ALLOWED / DENIED outcomes for later phases
    └── documents/           # runtime copies written by PDF ingestion (git-ignored)
```

## Generate, verify, reset

Run from `backend/` with `DATABASE_URL` set (migrations at head). Without flags, the generator creates (or completes) the dataset and verifies it. `--verify-only` checks it and writes nothing, and `--reset-demo-data` deletes demo records only.

```bash
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_system
.venv/bin/python scripts/generate_demo_dataset.py
.venv/bin/python scripts/generate_demo_dataset.py --verify-only
.venv/bin/python scripts/generate_demo_dataset.py --reset-demo-data
```

- **Deterministic.** There is no randomness and no timestamps. Every record ID is a UUIDv5 under a fixed namespace (see `id_strategy` in the manifest), and the PDFs are byte-identical on every run.
- **Idempotent.** A second run reports `0` created and `0` updated, and writes no files.
- **Never deletes during generation.** Generation creates missing demo records, corrects drifted fields on demo records and adds missing grants. It aborts before writing anything if a non-demo record already uses a demo natural key (e.g. an existing `HR_MANAGER` role or a demo email).
- **Ingestion.** PDFs go through the existing PDF ingestion pipeline (`ingest_pdf`), so documents and chunks are created exactly as an API upload would create them.
- **Reset.** Reset deletes only rows whose IDs are demo IDs, plus their stored PDFs under `data/documents/`. It never drops tables, touches migrations or deletes the committed files in `data/demo/`. It **refuses to run** while any non-demo record is linked to demo data, for example a real user placed in a demo department.

### Embeddings (opt-in, local)

Generation never embeds unless asked. To embed the 45 demo chunks with the configured provider (by default the local `sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions; no API key, and the model downloads once):

```bash
.venv/bin/python scripts/generate_demo_dataset.py --with-embeddings
```

Documents already fully embedded with the configured model are skipped, so a rerun changes nothing. If the provider is misconfigured, the command fails before writing anything.

## Verification

`--verify-only` and the tests check that:

- every PDF is valid, has the expected page count, the title, a heading and extractable text on every page, and matches a fresh deterministic rebuild;
- every key fact appears on exactly its declared page (and nowhere else in the corpus), which supports later citation tests;
- the manifests equal a fresh build from the spec;
- the database equals the manifest files: users, departments, role assignments, role permissions, document metadata, chunks covering every page, stored PDF checksums, and role/user grants equal to `access_matrix.json`, with no duplicate demo documents.

Tests: `tests/test_demo_dataset.py`. Run the suite against the dedicated test database, because several existing tests delete **all** documents:

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_system_test \
  .venv/bin/python -m unittest discover -s tests
```

## Example questions by source

| Question | Source |
|---|---|
| What does Nexora Technologies do? | Company_Overview p1 |
| What is the employee leave policy? | Employee_Handbook p2 |
| What is the annual performance review cycle? / salary bands? / HR escalation? | HR_Policy p2 / p3 / p5 |
| What is the Finance department budget? / Engineering allocation? | Finance_Report p2 |
| What was the quarterly procurement spend? | Procurement_Report p2 |
| What is the code review policy? / release requirements? / incident process? | Engineering_Guidelines p2 / p4 / p5 |
| What is the MFA policy? / security incident escalation? | Security_Policy p2 / p4 |
| How frequently are privileged accounts reviewed? | IT_Access_Control_Policy p3 |

## Structured data and OCR demo

After `alembic upgrade head` (migration `b2e5d8a1c4f3`), from `backend/`:

```bash
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_system
.venv/bin/python scripts/seed_structured_data.py --with-ocr
```

It is idempotent and additive: 8 projects, 2 compensation rows (Kabir Sethi INR 11.4 lakh, Rahul Gupta INR 6.2 lakh) and a synthetic scanned notice (`Facilities_Notice_Scan.png`, read by real OCR and granted to all six roles). Sample questions through `POST /api/v1/assistant/query`:

- Any user: "How many employees are in each department?", "What projects does the Finance department have and who leads them?", "When will the Pune office cafeteria be closed?" (answered from OCR text).
- Kabir Sethi: "What is my revised annual CTC?" (answered, INR 11.4 lakh) and "What is Rahul Gupta's revised annual CTC?" (refused: his row is not readable and the document is not granted).
- Meera Iyer (HR Manager): "What is Rahul Gupta's CTC?" (answered, `hr:read`). Vikram Nair (Finance Manager): "What is Kabir Sethi's salary?" (refused).

Upload your own: `POST /api/v1/documents/ingest` (PDF) or `/documents/ingest-image` (PNG/JPEG) as SUPER_ADMIN (the only demo role with `documents:write`). The upload is embedded immediately and is retrievable only by the uploader until grants are added.

## Submission runbook

Everything below was verified end to end on the `rag_system` demo database with real authentication, real OCR, the local embedding model and real Groq calls. No secret values appear here; keys live only in the git-ignored `backend/.env`.

### Environment requirements

- macOS or Linux, Python 3.12 (`backend/.venv`), Node 20.19 or newer, PostgreSQL 15 or newer with the `pgvector` extension.
- `backend/.env` (git-ignored) must contain `GROQ_API_KEY` and `JWT_SECRET_KEY`. Never put `DATABASE_URL` in it.
- Python packages: `cd backend && uv pip install --python .venv/bin/python -r requirements.txt` (includes `sentence-transformers` and `rapidocr-onnxruntime`; OCR needs no operating-system package).
- The embedding model `sentence-transformers/all-MiniLM-L6-v2` downloads once (about 90 MB) to `~/.cache/huggingface`. Keep that cache; with it in place add `HF_HUB_OFFLINE=1` to run without internet for embeddings (Groq still needs internet).

### Start PostgreSQL

```bash
brew services start postgresql@15
pg_isready -h localhost
```

Docker alternative: `cd backend && docker compose up -d postgres`. The demo data lives in the `rag_system` database; `rag_system_test` is for tests only.

### Start the backend (terminal 1)

```bash
cd backend
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_system
export HF_HUB_OFFLINE=1
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --port 8000
```

Check `http://localhost:8000/api/v1/ready` and the API docs at `http://localhost:8000/docs`. The first question after a cold start is slower while the local model loads.

### Start the frontend (terminal 2)

Follow [frontend/README.md](../../../frontend/README.md) (`npm install`, then `npm run dev`; open http://localhost:5173). The frontend files are owned by a separate effort and are not described here. Routes present in the repository: `/login`, `/app/chat` (assistant), `/app/upload` (PDF upload), `/app/upload-image` (image/OCR upload) and `/app/profile`. The two upload pages are shown in the navigation only to accounts the server reports with `documents:write` (SUPER_ADMIN in the demo).

### Log in

Use the demo-account cards on the login page, or `POST /api/v1/auth/login`. The accounts and their passwords are in the root README under "Hackathon Demo Accounts" (local demo use only): CEO / Super Admin `ishaan.malhotra@`, HR `meera.iyer@`, Finance `vikram.nair@`, Engineering `ananya.rao@`, Security `devika.krishnan@`, Employee `kabir.sethi@`, all `@nexora.example`. Only the SUPER_ADMIN account holds `documents:write`, so only it can upload.

### Upload a PDF

Frontend: the **Upload** page, `/app/upload` (SUPER_ADMIN). It makes one request and shows "Ready to search" only when the server reports `embedding_status: completed`; otherwise it offers Retry indexing, which calls the embeddings endpoint and never re-uploads. API: `POST /api/v1/documents/ingest`, `multipart/form-data` with field `file` (PDF, up to 25 MB) and a bearer token. The response includes `embedding_status` (`completed` means it is searchable now) and `embedding_model`. If it is `failed` or `not_configured`, retry with `POST /api/v1/embeddings/documents/{document_id}`; do not upload again. Only the uploader can retrieve a new document; sharing needs explicit grant rows.

### Upload an image for OCR

Frontend: the **Upload images** page, `/app/upload-image`. Like the PDF page, it requires `documents:write` (only SUPER_ADMIN in the demo; other accounts see "isn't available"). One request runs real OCR (RapidOCR, no operating-system install), stores the text as chunks, and embeds them with the local `all-MiniLM-L6-v2` model; Retry indexing is offered if embedding fails. API: `POST /api/v1/documents/ingest-image`, same shape, field `file`, PNG or JPEG up to 10 MB, `documents:write`. It runs real OCR, chunks, embeds and indexes in one request (`ocr_line_count`, `ocr_mean_confidence`, `embedding_status` in the response). No text found gives 422; OCR missing gives 503. Without the frontend, use `/docs` (Authorize with the login token, then "Try it out") or:

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' -d '{"email":"ishaan.malhotra@nexora.example","password":"<demo password>"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s -X POST localhost:8000/api/v1/documents/ingest-image -H "Authorization: Bearer $TOKEN" -F "file=@notice.png;type=image/png"
```

Use clear, printed text; phone photos of paper work less reliably. The seeded `Facilities_Notice_Scan.png` is already available to every role.

### Ask questions and inspect sources

Chat page, or `POST /api/v1/assistant/query` with `{"query": "...", "top_k": 5}`. The response lists `sources` (title, page or `image:ocr`, `source_type` of `pdf`, `image` or `structured`, and `cited`), plus `unverified_source_numbers`, `rejected_source_numbers` and `citation_check`. A citation proves the source was retrieved for this user; it does not prove the source supports each sentence. Good demo questions:

- Finance Manager: "What is the Finance department budget for FY 2025-26?" (answered, Finance Report) and "What are the HR salary bands?" (refused).
- Employee (Kabir): "What is my revised annual CTC?" (INR 11.4 lakh) and "What is Rahul Gupta's revised annual CTC?" (refused).
- Anyone: "How many employees are in each department?" (structured data) and "When will the Pune office cafeteria be closed?" (answered from OCR text).

### Known limitations and safe recovery

- **Groq free-tier limits are the main demo risk.** The configured key is limited to about 8,000 tokens per minute and a daily token allowance. A question uses roughly 2,000 to 3,000 tokens, so rapid-fire questions hit the minute limit and heavy rehearsal uses up the daily allowance. When it is exceeded the assistant returns HTTP 429, "The language model's rate limit has been reached", and the chat shows a retryable error. The provider waits once for a short `retry-after` (at most `LLM_RATE_LIMIT_MAX_WAIT_SECONDS`, default 45); a long one (the daily limit) fails at once. Recovery: wait and retry, rehearse sparingly before the presentation, or set `LLM_MODEL` to another Groq model, which has its own allowance.
- The frontend shows a rate limit (HTTP 429) as "The assistant is busy ... Please wait a moment and try again" with a Retry button. This handling exists in the frontend code; it was not exercised against a live 429 in a browser.
- What is and is not verified is listed in "Verification status" below.
- Citations are validated against the retrieved sources only; claim-by-claim support is not verified.
- New uploads are visible only to their uploader until grants are added. There is no sharing endpoint.
- OCR reads clear printed text best; word spacing can be imperfect.
- `employee_compensation` and `projects` hold only the synthetic rows listed above.
- If a demo question fails: check `curl localhost:8000/api/v1/ready`, then the backend terminal (log lines show a reason code and request ID, never the question or answer).
- **Never** run the test suite against `rag_system` (some tests delete documents). Tests: `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_system_test HF_HUB_OFFLINE=1 .venv/bin/python -m unittest discover -s tests`.
- Restore a damaged demo dataset (without touching users or grants): `.venv/bin/python scripts/generate_demo_dataset.py --verify-only` to check, then `.venv/bin/python scripts/generate_demo_dataset.py --with-embeddings` to complete missing records and embeddings, then `.venv/bin/python scripts/seed_structured_data.py --with-ocr`. All three are idempotent.

### Verification status

Nothing below was re-executed in the final handoff; it records what earlier runs showed.

**Verified live in a real browser** (real Vite dev server and proxy, real backend on `rag_system`, no Groq): login via the demo cards; the PDF page (one request, no separate embeddings call, "Ready to search" with the model named); the image page (one request, real OCR of a synthetic PNG, "Ready to search"); a fake image refused with the server's message; the Finance Manager sees no upload navigation and both pages say "isn't available" with no request sent. Temporary records from that run were deleted and the demo database matched its baseline.

**Verified through the API** (in-process app against `rag_system`, real login, real local embeddings, real OCR, real Groq `openai/gpt-oss-120b` with a recording wrapper; 22 of 22 checks in the final run): existing Finance Q&A with every source matching its database chunk; PDF upload, page-wise chunks, 384-dimension embeddings and uploader-only grant; OCR upload and answer from the image text; a structured headcount answer; five other accounts asked 15 questions with no temporary text in any response or in the sources sent to Groq.

**Previously reported test results (not rerun now):** backend 325 of 325 passed with none skipped (against `rag_system_test`); frontend 87 of 87 passed with TypeScript, lint and production build clean (frontend session's report).

**Not verified:** a live browser chat answer with Groq (the quota ran out first); a live browser retry-indexing click; a live 429 in the browser; other Groq models as a fallback; heavy concurrent use.

**Groq quota:** about 8,000 tokens per minute plus a daily allowance, and a question costs roughly 2,000 to 3,000 tokens. Heavy rehearsal exhausted the daily allowance during testing, so rehearse sparingly. If a limit is hit, the assistant returns 429 and the chat offers Retry; wait and retry, or set `LLM_MODEL` to another Groq model (untested).
