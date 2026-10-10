"""Part 6.3: authenticated assistant query endpoint.

A thin orchestration of existing services. The bearer token identifies the user (the
existing ``require_permission`` dependency); Part 6.1 builds context from
authorization-aware retrieval as that user; Part 6.2 generates an answer grounded only in
that context. Retrieval, access control, prompts and output validation live in those
services, not here.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dependencies import PERMISSION_DENIED, require_permission
from app.api.v1.embeddings import EMBEDDING_PROVIDER_FAILED, EMBEDDINGS_NOT_CONFIGURED
from app.db.session import get_session_factory
from app.schemas.rag import AssistantQueryResponse, AssistantSource, RagQuery
from app.services.authorization import AuthenticatedUser
from app.services.embeddings.provider import EmbeddingConfigurationError, EmbeddingProviderError
from app.services.embeddings.service import EmbeddingServiceError
from app.services.llm.provider import LLMConfigurationError
from app.services.rag.access_denial import ACCESS_DENIED_ANSWER, create_access_denial_probe
from app.services.rag.context import ContextAccessDeniedError
from app.services.rag.unified import create_context_builder
from app.services.rag.generation import (
    GenerationResult,
    RagGenerationError,
    create_answer_generator,
    usable_items,
)
from app.services.vector_search import VectorSearchError, VectorSearchExecutionError


router = APIRouter(prefix="/assistant", tags=["assistant"])
logger = logging.getLogger("app.rag")

LLM_NOT_CONFIGURED = "The language model is not configured."

# Generation failures keep their fixed, safe messages; only the HTTP status is chosen here.
_GENERATION_FAILURE_STATUS = {
    "invalid_context": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "unsafe_prompt": 422,
    "provider_timeout": status.HTTP_504_GATEWAY_TIMEOUT,
    "provider_rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
    "provider_error": status.HTTP_502_BAD_GATEWAY,
    "empty_output": status.HTTP_502_BAD_GATEWAY,
    "incomplete_output": status.HTTP_502_BAD_GATEWAY,
    "invalid_output": status.HTTP_502_BAD_GATEWAY,
}


@router.post(
    "/query",
    response_model=AssistantQueryResponse,
    responses={
        401: {"description": "Missing, malformed, invalid or expired bearer token, or an inactive account."},
        403: {"description": "The account lacks the documents:read permission."},
        422: {
            "description": "Invalid body (blank or over-long question, invalid top_k, unknown fields such as "
            "user_id or role), or a question that cannot be processed safely."
        },
        429: {"description": "The language model's rate limit is in effect; retry shortly."},
        500: {"description": "Internal error, including an inconsistent retrieval context. No details are returned."},
        502: {"description": "The embedding provider or the language model failed, or returned an empty, "
              "incomplete or invalid answer."},
        503: {"description": "The embedding provider or language model is not configured, or retrieval is unavailable."},
        504: {"description": "The language model did not respond in time."},
    },
)
async def query_assistant(
    query: RagQuery,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission("documents", "read")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> AssistantQueryResponse:
    """Answer a question from documents the authenticated user is authorized to read.

    The user comes only from the bearer token. Retrieval applies document authorization
    inside SQL before ranking and LIMIT, and the language model sees only that authorized
    context. With no usable authorized context, a fixed answer is returned without calling
    the model. When the question cannot be answered, an isolated server-side check may report
    ``access_denied`` (see ``access_denial.py``) instead of ``insufficient_context``. `sources` come from the server's retrieval; `unverified_source_numbers` are
    the model's own [S<n>] references and are not validated citations (Part 7).
    """
    request_id = getattr(request.state, "request_id", "unknown")
    try:
        # Both configurations are checked before any (paid) embedding call.
        generator = create_answer_generator()
        builder = create_context_builder(session_factory)
    except LLMConfigurationError:
        raise _failure(status.HTTP_503_SERVICE_UNAVAILABLE, LLM_NOT_CONFIGURED, "llm_not_configured", request_id)
    except EmbeddingConfigurationError:
        raise _failure(
            status.HTTP_503_SERVICE_UNAVAILABLE, EMBEDDINGS_NOT_CONFIGURED, "embeddings_not_configured", request_id
        )

    try:
        context = await builder.build(query, user, request_id=request_id)
    except ContextAccessDeniedError:
        raise _failure(status.HTTP_403_FORBIDDEN, PERMISSION_DENIED, "missing_permission", request_id)
    except EmbeddingConfigurationError:
        # Only the document path needs embeddings, so this surfaces when it is first used.
        raise _failure(
            status.HTTP_503_SERVICE_UNAVAILABLE, EMBEDDINGS_NOT_CONFIGURED, "embeddings_not_configured", request_id
        )
    except (EmbeddingProviderError, EmbeddingServiceError):
        raise _failure(status.HTTP_502_BAD_GATEWAY, EMBEDDING_PROVIDER_FAILED, "embedding_provider_failed", request_id)
    except VectorSearchExecutionError as exc:
        raise _failure(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc), "retrieval_failed", request_id)
    except VectorSearchError as exc:
        raise _failure(422, str(exc), "retrieval_rejected", request_id)

    try:
        result = await generator.generate(query, context, user=user, request_id=request_id)
    except RagGenerationError as exc:
        raise _failure(_GENERATION_FAILURE_STATUS[exc.category], str(exc), exc.category, request_id)

    if result.status != "answered":
        # The model could not answer. Decide, separately and from server-side rules only, whether
        # that is because the question targets information this user may not read. The probe
        # returns a bare boolean and never feeds the model; any failure means "not denied".
        usable = usable_items(result.context)
        probe = create_access_denial_probe(session_factory)
        if await probe.is_denied(
            query.query,
            user,
            best_authorized_similarity=max((item.similarity for item in usable), default=0.0),
            request_id=request_id,
        ):
            return _denied_response(request_id)

    return _to_response(result, request_id)


def _denied_response(request_id: str) -> AssistantQueryResponse:
    """The generic denial: no sources, no citations, no document or record details."""
    return AssistantQueryResponse(
        status="access_denied",
        answer=ACCESS_DENIED_ANSWER,
        request_id=request_id,
        sources=[],
        unverified_source_numbers=[],
        rejected_source_numbers=[],
        citation_check="not_applicable",
    )


def _failure(status_code: int, detail: str, reason: str, request_id: str) -> HTTPException:
    """A safe client error. Only the reason code and request ID are logged."""
    logger.warning("Assistant query failed reason=%s status=%d request_id=%s", reason, status_code, request_id)
    return HTTPException(status_code=status_code, detail=detail)


def _to_response(result: GenerationResult, request_id: str) -> AssistantQueryResponse:
    # Sources come from the server's authoritative context, never from the model's answer.
    cited = set(result.unverified_source_numbers)
    sources = (
        [
            AssistantSource(
                source_number=item.rank,
                document_id=item.document_id,
                document_title=item.document_title,
                chunk_id=item.chunk_id,
                page_number=item.page_number,
                source_locator=item.source_locator,
                similarity=item.similarity,
                source_type=item.source_type,
                cited=item.rank in cited,
            )
            for item in usable_items(result.context)
        ]
        if result.status == "answered"
        else []
    )
    return AssistantQueryResponse(
        status=result.status,
        answer=result.answer,
        request_id=request_id,
        sources=sources,
        unverified_source_numbers=list(result.unverified_source_numbers),
        rejected_source_numbers=list(result.rejected_source_numbers),
        citation_check=result.citation_check,
    )
