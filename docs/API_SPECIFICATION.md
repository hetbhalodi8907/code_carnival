# API Specification

All API paths below are planned. The exact request and response fields will be finalized during Phase 1.

## Authentication

### POST /api/v1/auth/login

Authenticates a user with username and password credentials.

Request:

```json
{
  "username": "student@example.edu",
  "password": "secret"
}
```

Response:

```json
{
  "access_token": "opaque-token",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "username": "student@example.edu",
    "roles": ["student"]
  }
}
```

## Documents

### POST /api/v1/documents

Uploads a PDF or image. Both operations are restricted to roles with ingestion permission.

Request fields:

- `title`: Human-readable title.
- `description`: Optional description.
- `source_type`: `pdf` or `image`.
- `access_policy`: `public`, `role`, or `private`.
- `role_names`: Required for role-based access.
- `file`: Binary file upload.

### GET /api/v1/documents

Lists documents visible to the authenticated user.

Response fields include `id`, `title`, `source_type`, `status`, `access_scope`, `created_at`, and `updated_at`.

### GET /api/v1/documents/{document_id}

Returns document metadata after document-level authorization.

## Structured records

### POST /api/v1/records

Creates a structured record with a document or collection association.

Request fields:

- `document_id`: Parent document or collection identifier.
- `payload`: Structured JSON object.
- `row_access_policy`: Policy for the record.
- `row_scope`: Owner, role, tenant, or explicit principals.

### GET /api/v1/records

Lists records visible to the authenticated user, including row-level filtering.

### GET /api/v1/records/{record_id}

Returns one record after document and row authorization.

## Ingestion

### POST /api/v1/ingestion/jobs

Starts an asynchronous ingestion job.

Request fields:

- `source_type`: `pdf`, `image`, or `record`.
- `source_id`: Existing source identifier.
- `force_reingest`: Optional boolean.

Response:

```json
{
  "job_id": "uuid",
  "status": "queued",
  "status_url": "/api/v1/ingestion/jobs/uuid"
}
```

### GET /api/v1/ingestion/jobs/{job_id}

Returns job status, progress, errors, and source identifiers.

## RAG

### POST /api/v1/chat/answer

Runs a permission-aware retrieval and answer-generation request.

Request:

```json
{
  "question": "What is the required laboratory procedure?",
  "max_sources": 5,
  "max_chunks_per_source": 4,
  "include_uncertainty": true
}
```

Response:

```json
{
  "answer": "The procedure requires...",
  "citations": [
    {
      "source_id": "uuid",
      "source_type": "pdf",
      "location": "page 4",
      "chunk_id": "uuid",
      "citation_text": "The procedure requires..."
    }
  ],
  "retrieval": {
    "authorized_chunks": 3,
    "unauthorized_chunks": 0
  },
  "uncertainty": null
}
```

The backend must return a safe error when no authorized context exists, rather than generating from an empty or unauthorized context.

## Health

### GET /api/v1/health

Returns service readiness and dependency status without exposing secret values.

## Error format

```json
{
  "error": {
    "code": "authorization_denied",
    "message": "The requested document is not available to this user.",
    "request_id": "uuid"
  }
}
```

## API security rules

- Require authentication on every protected route.
- Use HTTPS in production.
- Validate all request bodies with Pydantic.
- Apply authorization before returning data or invoking an LLM.
- Return generic error messages to clients.
- Do not expose provider response details unless they are needed for diagnostics and sanitized.
