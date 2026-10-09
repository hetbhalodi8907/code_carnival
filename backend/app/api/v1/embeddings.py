from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dependencies import require_permission
from app.db.session import get_session_factory
from app.schemas.embeddings import (
    EmbeddingStorageResult,
    VectorSearchRequest,
    VectorSearchResponse,
)
from app.services.authorization import AuthenticatedUser, can_access_document
from app.services.embeddings.provider import EmbeddingConfigurationError, EmbeddingProviderError
from app.services.embeddings.service import EmbeddingServiceError, create_embedding_service
from app.services.embeddings.storage import (
    DocumentHasNoChunksError,
    DocumentNotFoundError,
    EmbeddingStorageError,
    store_document_embeddings,
)
from app.services.vector_search import (
    VectorSearchError,
    VectorSearchExecutionError,
    VectorSearchService,
)


router = APIRouter()

EMBEDDINGS_NOT_CONFIGURED = "The embedding provider is not configured."
EMBEDDING_PROVIDER_FAILED = "The embedding provider could not generate embeddings."
DOCUMENT_NOT_FOUND = "The document does not exist."


@router.post(
    "/embeddings/documents/{document_id}",
    response_model=EmbeddingStorageResult,
    status_code=status.HTTP_200_OK,
)
async def generate_document_embeddings(
    document_id: UUID,
    user: AuthenticatedUser = Depends(require_permission("documents", "write")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> EmbeddingStorageResult:
    """Generate and persist embeddings for one document the caller is authorized to access."""
    async with session_factory() as session:
        authorized = await can_access_document(session, user.id, document_id)
    if not authorized:
        # Identical to a missing document, so existence is not revealed.
        raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND)
    try:
        service = create_embedding_service()
        result = await store_document_embeddings(
            document_id=document_id,
            session_factory=session_factory,
            service=service,
        )
    except EmbeddingConfigurationError as exc:
        raise HTTPException(status_code=503, detail=EMBEDDINGS_NOT_CONFIGURED) from exc
    except (EmbeddingProviderError, EmbeddingServiceError) as exc:
        raise HTTPException(status_code=502, detail=EMBEDDING_PROVIDER_FAILED) from exc
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DocumentHasNoChunksError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EmbeddingStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return EmbeddingStorageResult(**asdict(result))


@router.post(
    "/search/vector",
    response_model=VectorSearchResponse,
    status_code=status.HTTP_200_OK,
)
async def search_vectors(
    request: VectorSearchRequest,
    user: AuthenticatedUser = Depends(require_permission("documents", "read")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> VectorSearchResponse:
    """Nearest-chunk search over documents the authenticated user may access.

    The user comes only from the bearer token; authorization is applied inside the SQL
    query before ranking and LIMIT.
    """
    try:
        embedding_service = create_embedding_service()
        vector_search = VectorSearchService(
            session_factory,
            embedding_dimension=embedding_service.dimension,
            embedding_model=embedding_service.model,
        )
        results = await vector_search.search_text(
            request.query,
            top_k=request.top_k,
            embedding_service=embedding_service,
            user_id=user.id,
        )
    except EmbeddingConfigurationError as exc:
        raise HTTPException(status_code=503, detail=EMBEDDINGS_NOT_CONFIGURED) from exc
    except (EmbeddingProviderError, EmbeddingServiceError) as exc:
        raise HTTPException(status_code=502, detail=EMBEDDING_PROVIDER_FAILED) from exc
    except VectorSearchExecutionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except VectorSearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return VectorSearchResponse(
        query=request.query,
        top_k=request.top_k,
        embedding_model=embedding_service.model,
        results=[asdict(result) for result in results],
    )
