# Project Requirements

## 1. Purpose

Build a secure, multi-modal retrieval-augmented generation system for a college project. Users should be able to ask natural-language questions over PDFs, OCR-extracted image content, and structured database records while receiving concise answers with exact citations.

## 2. Functional requirements

### 2.1 Content ingestion

- Ingest PDF files and extract text with a PDF parser.
- Normalize text by removing formatting artifacts, preserving source locations, and creating a stable content representation.
- Ingest structured database rows through a documented ingestion contract.
- Ingest images and extract text with OCR.
- Assign every content item to a source document or source record and retain provenance.

### 2.2 Indexing and retrieval

- Split content into bounded, overlapping chunks.
- Generate embeddings for each chunk using a configurable embedding model.
- Store vectors and metadata in PostgreSQL with pgvector.
- Support semantic retrieval with a user-specific authorization predicate.
- Return candidate chunks with source, document, row, and permission metadata.

### 2.3 Authentication and authorization

- Authenticate users through a backend-controlled identity mechanism.
- Support roles such as student, instructor, researcher, and administrator where appropriate.
- Enforce document-level access control for content sources.
- Enforce row-level access control for structured data.
- Apply permissions in the retrieval query before candidate content is returned.
- Never retrieve unauthorized content and filter it only afterward in the LLM path.

### 2.4 RAG and answer generation

- Build a prompt from authorized context only.
- Use a configurable LLM provider through environment variables.
- Ask the model to answer only from the supplied context.
- Emit exact citations for every factual claim.
- Prevent citations from pointing to unauthorized or unprovided sources.

### 2.5 Assistant interface

- Provide a React frontend for asking questions and viewing answers.
- Use TypeScript, Tailwind CSS, and shadcn/ui components.
- Display citations, source type, document title, and authorization status.
- Display useful errors without exposing internal secrets or stack traces.

## 3. Non-functional requirements

- **Availability:** The backend and database must be deployable through Docker Compose.
- **Security:** Authorization must be enforced server-side and the application must not expose secrets.
- **Traceability:** Every indexed chunk must retain provenance and ingestion metadata.
- **Reliability:** Ingestion failures must be isolated, logged, and retryable.
- **Maintainability:** Backend modules should be modular and independently testable.
- **Performance:** Vector retrieval should use PostgreSQL and pgvector with query-time filters.
- **Observability:** Request, retrieval, authorization, ingestion, and model errors should be logged with correlation identifiers.
- **Portability:** Provider-specific assumptions should be isolated behind interfaces.
- **Data protection:** Passwords, API keys, and sensitive content must remain outside source control.

## 4. Scope boundaries

### In scope for the initial implementation

- Single application deployment with one PostgreSQL database.
- Basic role-based and document/row-based authorization.
- One configured embedding provider and one configurable LLM provider.
- PDF, image-OCR, and structured-record ingestion.
- Basic answer retrieval and citation validation.
- Security and prompt-injection tests.

### Deferred or out of scope for the initial implementation

- Multi-tenant authentication providers.
- Real-time streaming responses.
- Distributed vector search.
- Automatic policy management.
- Advanced observability platforms.
- High-volume batch ingestion.

## 5. Acceptance criteria

A query is accepted only when all of the following hold:

1. The user is authenticated.
2. The query passes basic input validation.
3. The retrieval query applies the user's effective permissions.
4. No unauthorized document, chunk, or row is returned to the LLM.
5. The model answer contains citations to authorized source identifiers.
6. Citation validation confirms that each cited source exists in the authorized context.
7. Unsupported or ungrounded claims are explicitly marked as uncertain or omitted.
8. Security tests verify that an unauthorized source cannot influence the answer.
