# Planned Database Schema

The schema is intentionally normalized and separates source metadata, access policy, content chunks, and model provenance. The exact SQLAlchemy models will be introduced in Phase 2.

```text
users
  id UUID PK
  username VARCHAR UNIQUE
  password_hash VARCHAR
  active BOOLEAN
  created_at TIMESTAMPTZ
  updated_at TIMESTAMPTZ

roles
  id UUID PK
  name VARCHAR UNIQUE
  description VARCHAR

user_roles
  user_id UUID FK users.id
  role_id UUID FK roles.id
  granted_at TIMESTAMPTZ

permissions
  id UUID PK
  principal_type VARCHAR  -- role or user
  principal_id UUID
  resource_type VARCHAR  -- document, record, collection
  resource_id UUID
  action VARCHAR          -- read, ingest, manage
  expires_at TIMESTAMPTZ
  created_at TIMESTAMPTZ

source_documents
  id UUID PK
  title VARCHAR
  description VARCHAR
  source_type VARCHAR    -- pdf, image, record, collection
  source_path VARCHAR
  storage_key VARCHAR
  checksum VARCHAR
  created_by UUID FK users.id
  status VARCHAR         -- pending, ready, failed, deleted
  access_scope VARCHAR   -- public, role, private
  created_at TIMESTAMPTZ
  updated_at TIMESTAMPTZ

structured_records
  id UUID PK
  document_id UUID FK source_documents.id
  payload JSONB
  row_access_scope VARCHAR
  row_owner_id UUID FK users.id
  row_role_names JSONB
  row_tenant_id UUID
  created_at TIMESTAMPTZ
  updated_at TIMESTAMPTZ

chunks
  id UUID PK
  source_type VARCHAR
  source_id UUID
  document_id UUID FK source_documents.id
  record_id UUID FK structured_records.id
  content TEXT
  content_hash VARCHAR
  page_number INTEGER NULL
  image_location VARCHAR NULL
  chunk_index INTEGER
  chunk_start INTEGER
  chunk_end INTEGER
  token_count INTEGER
  embedding_model VARCHAR
  embedding_version VARCHAR
  embedding VECTOR(384) NULL
  created_at TIMESTAMPTZ
  updated_at TIMESTAMPTZ

chunk_permissions
  chunk_id UUID FK chunks.id
  document_id UUID FK source_documents.id
  row_id UUID FK structured_records.id
  effective_scope VARCHAR
  granted_at TIMESTAMPTZ

ingestion_jobs
  id UUID PK
  source_type VARCHAR
  source_id UUID
  status VARCHAR
  error_message TEXT NULL
  started_at TIMESTAMPTZ
  completed_at TIMESTAMPTZ
  created_by UUID FK users.id
  input_metadata JSONB
  output_metadata JSONB

source_citations
  id UUID PK
  source_type VARCHAR
  source_id UUID
  document_id UUID FK source_documents.id
  record_id UUID FK structured_records.id
  citation_label VARCHAR
  location VARCHAR
  content_hash VARCHAR
  created_at TIMESTAMPTZ

query_logs
  id UUID PK
  request_id UUID
  actor_id UUID FK users.id
  query_hash VARCHAR
  result_count INTEGER
  authorization_result VARCHAR
  citation_validation_result VARCHAR
  created_at TIMESTAMPTZ
```

## Vector index design

- Store one embedding per chunk.
- Use a `vector` column with the configured model dimension.
- An index should be created only after the vector dimension is known.
- Apply the authorization predicates in the same SQL query as vector similarity search.
- Do not `SELECT` unauthorized chunks before applying permission filters.
- Store model name and version so an embedding cannot be accidentally reused across incompatible models.

## Source identity

Each source must have a stable UUID independent of its storage path. Source type and source identifier must be included in every citation. A PDF page and an image region should be represented as locations within their source identifier.

## Security schema notes

- Avoid storing raw passwords.
- Use database constraints for foreign keys and uniqueness.
- Use soft deletion or status state for documents instead of hard deletion when history is needed.
- Store policy changes in an audit table or operational log.
- Keep source text in a separate storage path when it is large, while retaining metadata and hashes in PostgreSQL.
