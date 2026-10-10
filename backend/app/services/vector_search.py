from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import contains_eager

from app import models
from app.services.authorization import document_access_condition
from app.services.embeddings.service import EmbeddingService


logger = logging.getLogger("app.vector_search")

DISTANCE_METRIC = "cosine"


class VectorSearchError(RuntimeError):
    """Raised when a vector search request is invalid."""


class VectorSearchExecutionError(VectorSearchError):
    """Raised when the database cannot execute a vector search."""


@dataclass(frozen=True)
class VectorSearchResult:
    chunk_id: UUID
    document_id: UUID
    document_title: str
    chunk_index: int
    page_number: int | None
    source_locator: str | None
    content: str
    distance: float
    similarity: float
    source_type: str = "pdf"
    """The owning document's source_type ("pdf" or "image"), read in the same statement."""


class VectorSearchService:
    """Perform bounded, authorization-aware cosine-distance retrieval from pgvector.

    Every search runs on behalf of a user. The document access predicate is part of the
    SQL WHERE clause built in ``_build_statement``, so PostgreSQL evaluates it before
    ORDER BY/LIMIT: unauthorized chunks are never selected, never consume a top-k slot
    and never reach Python. Results are not filtered after retrieval.
    """

    MAX_TOP_K = 20

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        embedding_dimension: int,
        embedding_model: str,
        max_top_k: int = MAX_TOP_K,
    ) -> None:
        if embedding_dimension <= 0:
            raise ValueError("Embedding dimension must be greater than zero.")
        if not embedding_model.strip():
            raise ValueError("Embedding model must not be empty.")
        if max_top_k <= 0:
            raise ValueError("Maximum top_k must be greater than zero.")
        self._session_factory = session_factory
        self._embedding_dimension = embedding_dimension
        self._embedding_model = embedding_model
        self._max_top_k = max_top_k

    async def search(
        self,
        query_embedding: Sequence[float],
        *,
        top_k: int,
        user_id: UUID,
        document_id: UUID | None = None,
    ) -> list[VectorSearchResult]:
        """Return the user's top_k authorized chunks ordered by ascending cosine distance.

        ``document_id`` narrows the search to one document. It is an extra condition in the same
        statement as the authorization predicate, so it can only ever REMOVE rows: a document the
        user may not read still yields nothing.
        """
        if not 1 <= top_k <= self._max_top_k:
            raise VectorSearchError(f"top_k must be between 1 and {self._max_top_k}.")
        if len(query_embedding) != self._embedding_dimension:
            raise VectorSearchError(
                f"Query embedding has length {len(query_embedding)}; "
                f"expected {self._embedding_dimension}."
            )
        if not all(isfinite(value) for value in query_embedding):
            raise VectorSearchError("Query embedding contains non-finite values.")

        session = self._session_factory()
        try:
            result = await session.execute(
                self._build_statement(list(query_embedding), top_k=top_k, user_id=user_id, document_id=document_id)
            )
            rows = result.all()
        except Exception as exc:
            # Database errors embed bound parameters (the full query vector).
            logger.error("Vector search failed error_type=%s", type(exc).__name__)
            raise VectorSearchExecutionError("Vector search failed.") from None
        finally:
            await session.close()

        return [
            VectorSearchResult(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=chunk.document.title,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                source_locator=chunk.source_locator,
                content=chunk.content,
                distance=float(distance),
                similarity=1.0 - float(distance),
                source_type=chunk.document.source_type,
            )
            for chunk, distance in rows
        ]

    async def search_text(
        self,
        query: str,
        *,
        top_k: int,
        embedding_service: EmbeddingService,
        user_id: UUID,
        document_id: UUID | None = None,
    ) -> list[VectorSearchResult]:
        """Embed a text query with the configured model, then search."""
        if not query.strip():
            raise VectorSearchError("Query cannot be empty.")
        if embedding_service.model != self._embedding_model:
            raise VectorSearchError("Query embedding model does not match the search model.")
        query_embedding = await embedding_service.embed_text(query)
        return await self.search(query_embedding, top_k=top_k, user_id=user_id, document_id=document_id)

    def _build_statement(
        self, query_embedding: list[float], *, top_k: int, user_id: UUID, document_id: UUID | None = None
    ) -> Select:
        distance = models.DocumentChunk.embedding.cosine_distance(query_embedding)
        statement = (
            select(models.DocumentChunk, distance.label("distance"))
            # Titles come from this same statement, so labelling results never needs a
            # second query.
            .join(models.DocumentChunk.document)
            .options(contains_eager(models.DocumentChunk.document))
            .where(models.DocumentChunk.embedding.is_not(None))
            .where(models.DocumentChunk.embedding_model == self._embedding_model)
            # Authorization is part of WHERE, so it is applied before ORDER BY/LIMIT.
            .where(document_access_condition(user_id, models.DocumentChunk.document_id))
            .order_by(distance, models.DocumentChunk.id)
            .limit(top_k)
        )
        if document_id is not None:
            # Scoped chat: the same WHERE clause, so it applies before ORDER BY and LIMIT.
            statement = statement.where(models.DocumentChunk.document_id == document_id)
        return statement
