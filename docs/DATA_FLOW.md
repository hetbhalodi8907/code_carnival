# Data Flow

## End-to-end data flow

```text
User selects or uploads content
             |
             v
PDF / Image / Database Record
             |
             v
Ingestion service
             |
             +--> PDF parser --> Text normalization --> Chunking
             |                                      |
             +--> OCR engine --> Text normalization --> Chunking
             |                                      |
             +--> Structured record normalization --> Chunking
                                                    |
                                                    v
                                      Embedding model + metadata
                                                    |
                                                    v
                              PostgreSQL + pgvector index
                                                    |
                                                    v
User asks a question
             |
             v
Authentication + authorization context
             |
             v
Query processing + embedding
             |
             v
Permission-aware vector query
             |
             +--> No matching authorized chunks --> Empty answer
             |
             v
Authorized chunks + source metadata only
             |
             v
LLM prompt
             |
             v
Model response
             |
             v
Citation validation against authorized sources
             |
             v
Response to frontend
```

## Ingestion data flow

1. A source is accepted through an API or scheduled ingestion process.
2. The source type is validated as PDF, image, or structured record.
3. Content is extracted or normalized.
4. Source provenance is recorded.
5. Permission metadata is resolved.
6. The content is split into chunks.
7. Embeddings are generated.
8. The chunks and metadata are written to PostgreSQL and pgvector.
9. Ingestion state and failures are logged.

## Query data flow

1. The user authenticates and receives an authorization context.
2. The request is validated.
3. The query is embedded with the configured embedding model.
4. PostgreSQL performs vector similarity search with document and row permission predicates.
5. Only candidates that pass all authorization checks are returned.
6. The backend constructs context using those authorized candidates only.
7. The LLM receives no unauthorized content.
8. The response is checked against the authorized source identifiers.
9. The validated response is returned to the frontend.

## Data classification

- Public: Visible to all authenticated users or anonymous users according to policy.
- Role-restricted: Visible only to assigned roles.
- Document-restricted: Visible only to users with document access.
- Row-restricted: Visible only to users with specific row access.
- Private: Visible only to the owner or an explicitly authorized administrator.

## Provenance requirements

Every normalized chunk must retain:

- Source type.
- Source identifier.
- Document identifier.
- Record identifier, when applicable.
- Page or image location.
- Ingestion timestamp.
- Content version.
- Permission scope.
- Chunk index and offset.
- Embedding model and vector version.
