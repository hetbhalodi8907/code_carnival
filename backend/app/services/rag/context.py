"""Part 6.1: query processing and secure context construction.

The builder's only data source is the authorization-aware ``VectorSearchService``. It
holds no database session, so it cannot run a query of its own, widen a search or
filter results in Python. Every context item is exactly one authorized search result,
kept in ranking order. Retrieved text is untrusted data: it is copied verbatim and
never interpreted. No LLM is called here; Part 6.2 consumes the structured context.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.schemas.rag import RagQuery
from app.services.authorization import AuthenticatedUser
from app.services.embeddings.service import EmbeddingService, create_embedding_service
from app.services.vector_search import VectorSearchResult, VectorSearchService


logger = logging.getLogger("app.rag")

ContextStatus = Literal["context_ready", "no_authorized_context"]


class ContextAccessDeniedError(PermissionError):
    """The user may not read documents, so no retrieval is attempted."""


class SecureSearch(Protocol):
    """The authorization-aware search contract (``VectorSearchService.search_text``)."""

    async def search_text(
        self,
        query: str,
        *,
        top_k: int,
        embedding_service: EmbeddingService,
        user_id: UUID,
        document_id: UUID | None = None,
    ) -> list[VectorSearchResult]: ...


@dataclass(frozen=True)
class ContextItem:
    """One authorized search result, as a citable source."""

    rank: int
    """1-based position in the secure ranking; also the source number in ``render``."""
    chunk_id: UUID
    document_id: UUID
    document_title: str
    chunk_index: int
    page_number: int | None
    source_locator: str | None
    content: str
    """Verbatim document text. Untrusted data, never instructions."""
    distance: float
    similarity: float
    source_type: str = "pdf"
    """Where the text came from: "pdf" (PDF text), "image" (OCR text) or "structured"
    (a database record). All are untrusted data; none is an instruction."""


@dataclass(frozen=True)
class ContextSource:
    """A document that contributed at least one context item."""

    document_id: UUID
    document_title: str


@dataclass(frozen=True)
class RetrievalContext:
    """Structured, deterministic context for one question by one authenticated user."""

    status: ContextStatus
    query: str
    top_k: int
    user_id: UUID
    items: tuple[ContextItem, ...]
    authorized_result_count: int
    """Results returned by secure retrieval, before the size budget."""
    omitted_result_count: int
    """Lowest-ranked authorized results left out by the size budget (whole items only)."""
    boundary: str
    """Token in every source delimiter, derived from the context itself (see ``render``)."""

    @property
    def has_context(self) -> bool:
        return bool(self.items)

    @property
    def sources(self) -> tuple[ContextSource, ...]:
        """Distinct documents in order of their first (best-ranked) item."""
        seen: dict[UUID, ContextSource] = {}
        for item in self.items:
            seen.setdefault(item.document_id, ContextSource(item.document_id, item.document_title))
        return tuple(seen.values())

    def render(self) -> str:
        """Plain-text source blocks with explicit, unforgeable boundaries.

        Each item sits between BEGIN/END lines that carry ``boundary``, a digest of the
        whole context. Document text cannot contain a line that matches it, because the
        digest covers that same text, so a document cannot fake a source boundary.
        """
        return "\n\n".join(_render_item(item, self.boundary) for item in self.items)


def _render_item(item: ContextItem, boundary: str) -> str:
    marker = f"SOURCE {item.rank} [{boundary}]"
    type_line = () if item.source_type == "pdf" else (f"Source Type: {item.source_type}",)
    return "\n".join(
        (
            f"--- BEGIN {marker} ---",
            f"Document: {item.document_title}",
            f"Document ID: {item.document_id}",
            *type_line,
            f"Page: {item.page_number if item.page_number is not None else 'unknown'}",
            f"Source Locator: {item.source_locator or 'unknown'}",
            f"Chunk ID: {item.chunk_id}",
            "Content:",
            item.content,
            f"--- END {marker} ---",
        )
    )


def _boundary(items: tuple[ContextItem, ...]) -> str:
    digest = hashlib.sha256()
    for item in items:
        for value in (item.chunk_id, item.document_id, item.document_title, item.page_number,
                      item.source_locator, item.content,
                      *(() if item.source_type == "pdf" else (item.source_type,))):
            digest.update(repr(value).encode())
            digest.update(b"\x00")
    return digest.hexdigest()[:16]


def _assemble(
    query: RagQuery,
    user_id: UUID,
    results: list[VectorSearchResult],
    max_context_characters: int,
) -> RetrievalContext:
    """Turn secure search results into context items, in their original order."""
    candidates = [
        ContextItem(
            rank=rank,
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            document_title=result.document_title,
            chunk_index=result.chunk_index,
            page_number=result.page_number,
            source_locator=result.source_locator,
            content=result.content,
            distance=result.distance,
            similarity=result.similarity,
            source_type=result.source_type,
        )
        for rank, result in enumerate(results, start=1)
    ]
    return assemble_context(query, user_id, candidates, max_context_characters)


def assemble_context(
    query: RagQuery,
    user_id: UUID,
    candidates: Sequence[ContextItem],
    max_context_characters: int,
) -> RetrievalContext:
    """Apply the size budget to already-authorized, ranked items and build the context.

    Callers (document search, structured retrieval) pass only items their own
    authorization-aware query returned; this function never fetches anything.
    """
    items: list[ContextItem] = []
    used = 0
    for candidate in candidates:
        # Keep a ranking prefix: stop at the first item that would exceed the budget.
        # The best item is always kept; one chunk is bounded by CHUNK_SIZE.
        if items and used + len(candidate.content) > max_context_characters:
            break
        used += len(candidate.content)
        items.append(candidate)

    kept = tuple(items)
    return RetrievalContext(
        status="context_ready" if kept else "no_authorized_context",
        query=query.query,
        top_k=query.top_k,
        user_id=user_id,
        items=kept,
        authorized_result_count=len(candidates),
        omitted_result_count=len(candidates) - len(kept),
        boundary=_boundary(kept),
    )


class ContextBuilder:
    """Build RAG context for an authenticated user from secure retrieval only."""

    def __init__(
        self,
        search: SecureSearch,
        embedding_service: EmbeddingService,
        *,
        max_context_characters: int | None = None,
    ) -> None:
        budget = settings.rag_max_context_characters if max_context_characters is None else max_context_characters
        if budget <= 0:
            raise ValueError("The context budget must be greater than zero.")
        self._search = search
        self._embedding_service = embedding_service
        self._max_context_characters = budget

    async def build(
        self,
        query: RagQuery,
        user: AuthenticatedUser,
        *,
        request_id: str | None = None,
        document_id: UUID | None = None,
        search_text: str | None = None,
    ) -> RetrievalContext:
        """Retrieve the user's authorized chunks for ``query`` and structure them.

        ``document_id`` restricts retrieval to one document (still only if the user may read it).
        ``search_text`` replaces the text that is EMBEDDED for the search (used for short follow-up
        questions); the context and the generated answer still belong to ``query`` itself.

        Embedding-provider and search failures propagate unchanged: they are errors, not
        an empty context. An empty context means retrieval succeeded with no authorized
        results.
        """
        if not isinstance(query, RagQuery):
            raise TypeError("query must be a validated RagQuery.")
        if not user.has_permission("documents", "read"):
            logger.info(
                "RAG context denied reason=missing_permission user_id=%s request_id=%s",
                user.id,
                request_id,
            )
            raise ContextAccessDeniedError("The user may not read documents.")

        started = time.perf_counter()
        # Only passed when set, so every existing search implementation keeps its signature.
        scope = {} if document_id is None else {"document_id": document_id}
        results = await self._search.search_text(
            search_text or query.query,
            top_k=query.top_k,
            embedding_service=self._embedding_service,
            user_id=user.id,
            **scope,
        )
        context = _assemble(query, user.id, results, self._max_context_characters)
        # Counts only: never the question, chunk text or the context itself.
        logger.info(
            "RAG context built user_id=%s status=%s authorized_results=%d context_items=%d "
            "omitted=%d duration_ms=%.2f request_id=%s",
            user.id,
            context.status,
            context.authorized_result_count,
            len(context.items),
            context.omitted_result_count,
            (time.perf_counter() - started) * 1000,
            request_id,
        )
        return context


def create_context_builder(session_factory: async_sessionmaker[AsyncSession]) -> ContextBuilder:
    """Wire the builder to the configured embedding model and the secure vector search.

    Raises ``EmbeddingConfigurationError`` when no embedding provider is configured.
    """
    embedding_service = create_embedding_service()
    search = VectorSearchService(
        session_factory,
        embedding_dimension=embedding_service.dimension,
        embedding_model=embedding_service.model,
    )
    return ContextBuilder(search, embedding_service)
