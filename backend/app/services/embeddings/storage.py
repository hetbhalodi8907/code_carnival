from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import models
from app.services.embeddings.provider import EmbeddingConfigurationError, EmbeddingProviderError
from app.services.embeddings.service import EmbeddingService, EmbeddingServiceError


logger = logging.getLogger("app.embeddings")


class EmbeddingStorageError(RuntimeError):
    """Raised when document embeddings cannot be generated or persisted."""


class DocumentNotFoundError(EmbeddingStorageError):
    """Raised when the requested document does not exist."""


class DocumentHasNoChunksError(EmbeddingStorageError):
    """Raised when the requested document has no chunks to embed."""


@dataclass(frozen=True)
class EmbeddingStorageResult:
    document_id: UUID
    chunks_processed: int
    embeddings_created: int
    embedding_model: str
    status: str


async def store_document_embeddings(
    *,
    document_id: UUID,
    session_factory: async_sessionmaker[AsyncSession],
    service: EmbeddingService,
) -> EmbeddingStorageResult:
    """Generate and persist embeddings for all chunks of one document in one transaction."""
    session = session_factory()
    try:
        document_result = await session.execute(
            select(models.Document.id).where(models.Document.id == document_id)
        )
        if document_result.scalar_one_or_none() is None:
            raise DocumentNotFoundError("The document does not exist.")

        # Lock only this document's chunk rows: a concurrent retry waits, then finds them embedded and
        # does no provider work. Readers (vector search) are never blocked.
        chunks_result = await session.execute(
            select(models.DocumentChunk)
            .where(models.DocumentChunk.document_id == document_id)
            .order_by(models.DocumentChunk.chunk_index)
            .with_for_update()
        )
        chunks = chunks_result.scalars().all()
        if not chunks:
            raise DocumentHasNoChunksError("The document has no chunks to embed.")

        # Only chunks without a vector from THIS model are embedded. A retry after a failure costs
        # nothing for chunks that already have one; vectors from another model are not searchable
        # under this model, so they are regenerated.
        pending = [chunk for chunk in chunks if chunk.embedding is None or chunk.embedding_model != service.model]
        vectors = await service.embed_texts([chunk.content for chunk in pending]) if pending else []
        for chunk, vector in zip(pending, vectors, strict=True):
            chunk.embedding = vector
            chunk.embedding_model = service.model

        await session.commit()
    except (EmbeddingStorageError, EmbeddingProviderError, EmbeddingServiceError):
        await session.rollback()
        raise
    except Exception as exc:
        await session.rollback()
        # Database errors embed bound parameters (full vectors), so only the type is logged.
        logger.error("Embedding persistence failed error_type=%s", type(exc).__name__)
        raise EmbeddingStorageError("Document embeddings could not be persisted.") from None
    finally:
        await session.close()

    return EmbeddingStorageResult(
        document_id=document_id,
        chunks_processed=len(chunks),
        embeddings_created=len(vectors),  # newly created now; 0 when every chunk was already embedded
        embedding_model=service.model,
        status="completed",
    )


EmbeddingOutcome = Literal["completed", "failed", "not_configured"]


@dataclass(frozen=True)
class IngestEmbeddingResult:
    status: EmbeddingOutcome
    model: str | None
    """The embedding model used; None unless ``status`` is "completed"."""


async def embed_ingested_document(
    *,
    document_id: UUID,
    session_factory: async_sessionmaker[AsyncSession],
    service: EmbeddingService | None = None,
) -> IngestEmbeddingResult:
    """Embed a just-ingested document with the configured model so it is searchable at once.

    Used by every upload path (PDF and image). A missing or failing embedding provider never
    fails the upload: the document stays stored, unsearchable until embedded (retry with
    ``POST /embeddings/documents/{id}``), and the outcome is reported to the caller. Only the
    outcome is logged, never text.
    """
    try:
        if service is None:
            from app.services.embeddings.service import create_embedding_service

            service = create_embedding_service()
        result = await store_document_embeddings(
            document_id=document_id, session_factory=session_factory, service=service
        )
    except EmbeddingConfigurationError:
        outcome: EmbeddingOutcome = "not_configured"
    except (EmbeddingProviderError, EmbeddingServiceError, EmbeddingStorageError):
        outcome = "failed"
    except Exception as exc:  # noqa: BLE001 - the upload is already stored; any other failure must not turn it into a 500
        logger.error("Embedding failed unexpectedly error_type=%s", type(exc).__name__)
        outcome = "failed"
    else:
        return IngestEmbeddingResult("completed", result.embedding_model)
    logger.warning("Ingested document left without embeddings document_id=%s outcome=%s", document_id, outcome)
    return IngestEmbeddingResult(outcome, None)
