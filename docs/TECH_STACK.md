# Technology Stack

## Backend

- Python 3.11 or later.
- FastAPI for HTTP APIs and OpenAPI documentation.
- Pydantic for request and response validation.
- SQLAlchemy for database access and migrations.
- Alembic for schema migrations.
- PostgreSQL as the primary relational and vector database.
- pgvector for vector storage and similarity search.
- Pydantic Settings for environment configuration.
- Python logging for structured operational logs.
- HTTPX for external model and ingestion service calls.

## Data processing

- PDF processing through a selected parser such as a maintained PDF extraction library.
- OCR through a selected OCR engine, with image preprocessing kept behind an abstraction.
- Embedding model through a provider adapter.
- LLM provider through a provider adapter.
- Chunking through a deterministic, configurable chunking service.

## Authentication and authorization

- Password hashing with a maintained password-hashing library.
- Session or bearer-token authentication implemented in the backend.
- Role and permission checks delegated to server-side authorization services.
- Authorization context passed explicitly into retrieval and RAG operations.

## Frontend

- React 18 or later.
- TypeScript.
- Vite for local development and builds.
- Tailwind CSS.
- shadcn/ui components.
- React Hook Form for form handling.
- TanStack Query for server-state management, if selected.
- Lucide icons for UI symbols.

## Infrastructure

- Docker for backend and application services.
- Docker Compose for local development.
- PostgreSQL container with pgvector enabled.
- Environment-file configuration through `.env.example` and runtime environment variables.
- Production deployment should use a managed PostgreSQL service and managed secrets.

## Testing

- Pytest for backend unit and integration tests.
- HTTPX for API tests.
- SQLAlchemy test database support for repository tests.
- Playwright for frontend end-to-end tests.
- Security test fixtures that create authorized and unauthorized documents, chunks, and rows.

## Dependency policy

Dependencies will be added only when they provide a clear architectural need. No dependency will be installed during the documentation-only phase.
