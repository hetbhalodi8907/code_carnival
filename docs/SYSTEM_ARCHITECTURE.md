# System Architecture

## High-level architecture

```text
+---------------------------------------------------------------+
|                         React Web Client                         |
|  Search / Chat UI | Citations | Permissions | Error states      |
+-------------------------------+-------------------------------+
                                |
                                | HTTPS / JSON API
                                v
+---------------------------------------------------------------+
|                         FastAPI Backend                          |
|  Authentication | Authorization | API | RAG Orchestrator       |
+-------------------------------+-------------------------------+
|                                |                                   |
|                                |                                   |
|                                v                                   v
+---------------------------------------------------------------+   +-------------------------------+
| PostgreSQL + pgvector            |   | Configurable LLM Provider     |
| Documents | Chunks | Embeddings  |   | OpenAI-compatible or other    |
| Rows | Permissions | Metadata     |   | provider adapter              |
+---------------------------------------------------------------+   +-------------------------------+
                                ^
                                |
                                | Embedding provider adapter
+                                v
+---------------------------------------------------------------+
|          Configurable Embedding Model Provider                 |
+---------------------------------------------------------------+

+---------------------------------------------------------------+
| PDF / Image / Structured Data Sources                         |
| Ingestion Workers | OCR | Normalization | Provenance             |
+---------------------------------------------------------------+
```

## Component responsibilities

### React frontend

- Collects user queries and displays answers.
- Uses backend-issued authentication context.
- Shows source citations and permission-aware results.
- Must not make authorization decisions or contain secret values.

### FastAPI backend

- Handles authentication and request validation.
- Builds an authorization context for each request.
- Coordinates ingestion, retrieval, and answer generation.
- Enforces permission predicates before data reaches the LLM.
- Applies provider adapters and citation validation.
- Logs security-sensitive events without leaking secrets.

### PostgreSQL and pgvector

- Stores documents, source metadata, structured records, permissions, chunks, embeddings, and ingestion state.
- Performs permission-aware vector search.
- Stores immutable or versioned source provenance.
- Enforces database-level constraints and foreign keys.

### Ingestion pipeline

- PDF parser extracts text and preserves page numbers.
- Image pipeline preprocesses images and runs OCR.
- Structured ingestion normalizes records.
- Each extracted chunk is associated with its source and permissions.

### Retrieval and RAG orchestrator

- Translates a query into a permission-aware search request.
- Retrieves only authorized candidate chunks.
- Adds the authorized content and source metadata to the LLM context.
- Validates citations before returning the final response.

## Security architecture principles

- Authorization is performed in the backend retrieval query.
- The LLM receives authorized context only.
- The prompt contains no hidden or unauthorized content.
- Source identifiers are validated against the retrieval result.
- Prompt text cannot change the authorization policy.
- All external API calls use short timeouts and retry policies where appropriate.

## Deployment shape

The initial development deployment will use a single backend process, a PostgreSQL container, and a local frontend build. Production should use managed services and environment-provided credentials.
