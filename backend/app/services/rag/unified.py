"""Part 10: one context builder over every retrieval path.

``UnifiedContextBuilder.build(query, user)`` has the same contract as the Part 6.1
``ContextBuilder``, so the assistant pipeline (generation, citation validation, response)
is unchanged. It only decides WHERE the authorized context comes from:

1. A deterministic router (no LLM) maps the question to a structured-data intent, if any.
   The structured path runs a fixed parameterized SQL statement whose WHERE clause enforces
   row-level access (see ``structured.py``).
2. If there is no structured intent, or the structured query returned no authorized rows,
   the question goes to the document path: authorization-aware vector search over PDF text
   AND OCR text from images (both are ``documents``, with the same grants).

Either way every item in the context was returned by an authorization-aware query for
THIS user before it was assembled. Nothing is fetched or filtered afterwards, so the model
only ever sees authorized content.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.schemas.rag import RagQuery
from app.services.authorization import AuthenticatedUser
from app.services.rag.context import (
    ContextAccessDeniedError,
    ContextBuilder,
    RetrievalContext,
    assemble_context,
    create_context_builder as create_document_context_builder,
)
from app.services.rag.structured import StructuredRetriever, classify_question


logger = logging.getLogger("app.rag")


class UnifiedContextBuilder:
    def __init__(
        self,
        structured: StructuredRetriever,
        document_builder_factory: Callable[[], ContextBuilder],
        *,
        max_context_characters: int | None = None,
    ) -> None:
        self._structured = structured
        # Lazy: a structured question must not need the embedding model.
        self._document_builder_factory = document_builder_factory
        self._budget = settings.rag_max_context_characters if max_context_characters is None else max_context_characters

    async def build(
        self,
        query: RagQuery,
        user: AuthenticatedUser,
        *,
        request_id: str | None = None,
    ) -> RetrievalContext:
        if not isinstance(query, RagQuery):
            raise TypeError("query must be a validated RagQuery.")
        if not user.has_permission("documents", "read"):
            logger.info("RAG context denied reason=missing_permission user_id=%s request_id=%s", user.id, request_id)
            raise ContextAccessDeniedError("The user may not read documents.")

        directory = await self._structured.load_directory()
        intent = classify_question(query.query, directory)
        if intent is not None:
            items = await self._structured.retrieve(intent, user.id)
            logger.info(
                "RAG route path=structured intent=%s authorized_rows=%d user_id=%s request_id=%s",
                intent.name, len(items), user.id, request_id,
            )
            if items:
                return assemble_context(query, user.id, items, self._budget)
            # No row this user may read (or none exists): continue with authorized documents.

        logger.info("RAG route path=documents user_id=%s request_id=%s", user.id, request_id)
        return await self._document_builder_factory().build(query, user, request_id=request_id)


def create_context_builder(session_factory: async_sessionmaker[AsyncSession]) -> UnifiedContextBuilder:
    """Wire the structured retriever and the (lazily created) document builder."""
    return UnifiedContextBuilder(
        StructuredRetriever(session_factory),
        lambda: create_document_context_builder(session_factory),
    )
