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

### Embeddings (opt-in, external cost)

Generation **never** calls an external API. To embed the demo chunks with the existing Part 4 embedding service:

```bash
OPENAI_API_KEY=... .venv/bin/python scripts/generate_demo_dataset.py --with-embeddings
```

This sends all 45 chunks (about 35,000 characters, roughly 9,000 tokens) to the configured provider (`text-embedding-3-small`). Documents that are already fully embedded with the configured model are skipped. Without a key, the command fails before writing anything.

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
