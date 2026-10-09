"""Embedding provider and service abstractions."""

from app.services.embeddings.provider import (
    EmbeddingConfigurationError,
    EmbeddingProvider,
    EmbeddingProviderError,
    OpenAIEmbeddingProvider,
)
from app.services.embeddings.service import (
    EmbeddingService,
    EmbeddingServiceError,
    create_embedding_service,
)

__all__ = [
    "EmbeddingConfigurationError",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingService",
    "EmbeddingServiceError",
    "OpenAIEmbeddingProvider",
    "create_embedding_service",
]
