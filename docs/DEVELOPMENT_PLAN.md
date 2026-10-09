# Development Plan

## Phase 0 — Project initialization

- Confirm workspace and repository boundaries.
- Create the documentation and progress-control structure.
- Define the project scope, architecture, and security principles.
- Establish the required implementation sequence.

**Status:** Completed.

## Phase 1 — Backend foundation

- Create the Python package structure.
- Add FastAPI application configuration and health endpoint.
- Add Pydantic request and response models.
- Add centralized logging and environment configuration.
- Add dependency and development commands.
- Add initial automated tests for configuration and API contracts.

**Status:** Next task.

## Phase 2 — PostgreSQL and database

- Add PostgreSQL and pgvector configuration.
- Create initial migrations with Alembic.
- Add SQLAlchemy models for users, roles, permissions, documents, records, chunks, and ingestion jobs.
- Add indexes and vector dimension configuration.
- Add test database setup.

## Phase 3 — PDF ingestion

- Add a PDF parser abstraction.
- Normalize extracted text and preserve page locations.
- Add source metadata, checksums, and ingestion jobs.
- Add document-level access policy assignment.
- Add durable ingestion tests.

## Phase 4 — Embeddings and vector search

- Add an embedding provider abstraction.
- Add deterministic chunking.
- Store embeddings and metadata in PostgreSQL.
- Add vector similarity search tests.
- Add model and vector-version validation.

## Phase 5 — Authentication and authorization

- Add user authentication and token handling.
- Add role and permission models.
- Add document-level and row-level checks.
- Add authorization audit logging.
- Add tests for denied and allowed queries.

## Phase 6 — Secure RAG

- Add the permission-aware retrieval service.
- Build the authorized context block.
- Add the configurable LLM provider adapter.
- Add prompt-injection isolation and response schema validation.
- Add tests proving unauthorized data never reaches the LLM.

## Phase 7 — Citations and grounding

- Assign stable source identifiers and locations.
- Validate model citations against authorized context.
- Add exact source citation tests.
- Add uncertainty and unsupported-claim handling.
- Add source attribution to API responses.

## Phase 8 — Structured database retrieval

- Add structured-record ingestion.
- Add row-level permission predicates.
- Add relationship-aware query handling.
- Add integration tests for record access and denial.

## Phase 9 — OCR

- Add image upload and preprocessing.
- Add OCR engine abstraction.
- Normalize OCR output and retain image coordinates.
- Add OCR ingestion and source attribution tests.

## Phase 10 — AI assistant API

- Add the chat endpoint using the secure RAG pipeline.
- Add rate limiting and input limits.
- Add request correlation and operational logging.
- Add API-level integration tests.

## Phase 11 — Frontend

- Scaffold the React and TypeScript application.
- Add authentication and protected routes.
- Build the chat, citation, and source-view interfaces.
- Use Tailwind CSS and shadcn/ui components.
- Add frontend testing and error states.

## Phase 12 — Security testing

- Test authorization bypasses and client-side tampering.
- Test prompt injection in PDF, image, and database content.
- Test citation fabrication and source mismatch.
- Test oversized inputs and malformed files.
- Test leaked secrets and cross-user data access.
- Review threat model and remediation status.

## Phase 13 — Integration and demo

- Run the full local Docker Compose system.
- Validate ingestion, retrieval, authorization, citations, and frontend behavior.
- Add demonstration documents and roles.
- Create setup and usage documentation.
- Run final test and security verification.

## Delivery sequence

The implementation should proceed one phase at a time. Phase 5 authorization must precede Phase 6 secure RAG, and Phase 7 citation validation must precede the public assistant endpoint.
