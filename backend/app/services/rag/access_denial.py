"""Explicit "access denied" signal for questions that target information the user may not read.

Without this, a question about restricted content looks like any other unanswered question:
retrieval returns the user's best AUTHORIZED chunks (irrelevant to the question), and the model
correctly says the context is insufficient. This module adds a separate, isolated check that runs
only AFTER the assistant has already failed to answer, so it can never influence an answer:

1. Policy check (deterministic): the question names a person's confidential compensation, or the
   user's own, and the compensation access rule says this user may not read it. Only the rule is
   evaluated (a boolean); no compensation row is read.
2. Relevance probe: the question is embedded and ONE aggregate query measures how similar it is
   to documents the user may NOT read. The statement selects a single number (the best
   similarity): no chunk text, ids, titles or filenames are ever selected, so nothing restricted
   exists in Python, in the model context, in logs or in the response. Denial needs both a high
   similarity and a clear lead over the user's best authorized match.

The result is a bare boolean. Any error, missing embedding configuration or ambiguity means "not
denied", which preserves the ordinary insufficient-information answer. The language model is never
asked to decide access, and nothing here widens what the user can read.

Honest limitation: telling a user "access denied" instead of "insufficient information" reveals
that restricted material relevant to the question exists. That is the purpose of the feature; the
probe reveals nothing else about it.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import Uuid, func, literal, not_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import models
from app.core.config import settings
from app.services.authorization import AuthenticatedUser, document_access_condition
from app.services.embeddings.service import EmbeddingService, create_embedding_service
from app.services.rag.structured import StructuredRetriever, classify_question, compensation_access


logger = logging.getLogger("app.rag")

ACCESS_DENIED_ANSWER = "You don't have permission to access the information requested."


def restricted_distance_statement(vector: list[float], embedding_model: str, user_id: UUID):
    """One aggregate over documents the user may NOT read: a single number (the smallest cosine
    distance) comes back. No chunk text, ids, titles or filenames are selected."""
    distance = models.DocumentChunk.embedding.cosine_distance(vector)
    return (
        select(func.min(distance))
        .select_from(models.DocumentChunk)
        .where(models.DocumentChunk.embedding.is_not(None))
        .where(models.DocumentChunk.embedding_model == embedding_model)
        .where(not_(document_access_condition(user_id, models.DocumentChunk.document_id)))
    )


class AccessDenialProbe:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        structured: StructuredRetriever | None = None,
        embedding_service: EmbeddingService | None = None,
        min_similarity: float | None = None,
        margin: float | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._structured = structured or StructuredRetriever(session_factory)
        self._embedding_service = embedding_service
        self._min_similarity = settings.access_denial_min_similarity if min_similarity is None else min_similarity
        self._margin = settings.access_denial_margin if margin is None else margin

    async def is_denied(
        self,
        query: str,
        user: AuthenticatedUser,
        *,
        best_authorized_similarity: float,
        request_id: str | None = None,
    ) -> bool:
        """True only when access denial is established; never raises."""
        try:
            if await self._compensation_denied(query, user.id):
                logger.info("Access denial signal=policy user_id=%s request_id=%s", user.id, request_id)
                return True
            if await self._restricted_documents_match(query, user.id, best_authorized_similarity):
                logger.info("Access denial signal=relevance user_id=%s request_id=%s", user.id, request_id)
                return True
        except Exception as exc:  # noqa: BLE001 - a failing probe must degrade to "insufficient", never to an error
            logger.warning("Access denial probe unavailable error_type=%s request_id=%s", type(exc).__name__, request_id)
        return False

    async def _compensation_denied(self, query: str, user_id: UUID) -> bool:
        """The question targets compensation the access rule does not let this user read."""
        intent = classify_question(query, await self._structured.load_directory())
        if intent is None:
            return False
        if intent.name == "my_compensation":
            target: UUID | None = user_id
        elif intent.name == "employee_compensation":
            target = intent.target_user_id
        else:
            return False
        if target is None:
            return False
        async with self._session_factory() as session:
            allowed = await session.scalar(select(compensation_access(user_id, literal(target, type_=Uuid))))
        return allowed is False

    async def _restricted_documents_match(self, query: str, user_id: UUID, best_authorized: float) -> bool:
        service = self._embedding_service or create_embedding_service()
        vector = await service.embed_text(query)
        statement = restricted_distance_statement(vector, service.model, user_id)
        async with self._session_factory() as session:
            best_distance = await session.scalar(statement)
        if best_distance is None:
            return False
        restricted = 1.0 - float(best_distance)
        return restricted >= self._min_similarity and restricted >= best_authorized + self._margin


def create_access_denial_probe(session_factory: async_sessionmaker[AsyncSession]) -> AccessDenialProbe:
    return AccessDenialProbe(session_factory)
