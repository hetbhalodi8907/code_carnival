from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from math import isfinite
from typing import Any

from app.core.config import settings
from app.models.document_chunk import EMBEDDING_VECTOR_DIMENSION


logger = logging.getLogger("app.embeddings")

SUPPORTED_EMBEDDING_PROVIDERS = frozenset({"openai"})


class EmbeddingProviderError(RuntimeError):
    """Raised when an embedding provider cannot produce a valid response."""


class EmbeddingConfigurationError(ValueError):
    """Raised when the embedding provider configuration is missing or inconsistent."""


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def model(self) -> str:
        """Identifier of the model that produced the embeddings."""

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Generate one embedding for a non-empty text value."""

    @abstractmethod
    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate embeddings for a non-empty batch of text values."""


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI text embedding provider with strict dimension validation."""

    def __init__(
        self,
        *,
        client: Any,
        model: str,
        dimension: int,
    ) -> None:
        if not model.strip():
            raise ValueError("Embedding model must not be empty.")
        if dimension <= 0:
            raise ValueError("Embedding dimension must be greater than zero.")
        self._client = client
        self._model = model
        self._dimension = dimension

    @property
    def model(self) -> str:
        return self._model

    async def embed_text(self, text: str) -> list[float]:
        if not text.strip():
            raise EmbeddingProviderError("Embedding input cannot be empty.")
        vectors = await self.embed_texts([text])
        return vectors[0]

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            raise EmbeddingProviderError("Embedding input cannot be empty.")
        if any(not text.strip() for text in texts):
            raise EmbeddingProviderError("Embedding input cannot contain empty text.")

        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=list(texts),
                encoding_format="float",
            )
        except Exception as exc:
            # Provider messages can echo request details, so only the type is logged.
            logger.warning("Embedding provider request failed error_type=%s", type(exc).__name__)
            raise EmbeddingProviderError("The embedding provider request failed.") from exc

        vectors = _parse_vectors(response)
        if len(vectors) != len(texts):
            raise EmbeddingProviderError(
                f"Provider returned {len(vectors)} vectors for {len(texts)} inputs."
            )
        for index, vector in enumerate(vectors):
            if len(vector) != self._dimension:
                raise EmbeddingProviderError(
                    f"Embedding vector {index} has length {len(vector)}; expected {self._dimension}."
                )
        return vectors


def _parse_vectors(response: Any) -> list[list[float]]:
    """Convert a provider response into float vectors, rejecting malformed payloads."""
    try:
        items = list(response.data)
        raw_vectors = [list(item.embedding) for item in items]
    except (AttributeError, TypeError) as exc:
        raise EmbeddingProviderError("The embedding provider returned a malformed response.") from exc

    vectors: list[list[float]] = []
    for index, raw_vector in enumerate(raw_vectors):
        if not all(
            isinstance(value, (int, float)) and not isinstance(value, bool) for value in raw_vector
        ):
            raise EmbeddingProviderError(f"Embedding vector {index} contains non-numeric values.")
        vector = [float(value) for value in raw_vector]
        if not all(isfinite(value) for value in vector):
            raise EmbeddingProviderError(f"Embedding vector {index} contains non-finite values.")
        vectors.append(vector)
    return vectors


def validate_embedding_configuration() -> None:
    """Fail fast when settings cannot produce vectors that fit the database schema."""
    if settings.embedding_provider not in SUPPORTED_EMBEDDING_PROVIDERS:
        raise EmbeddingConfigurationError(
            f"Unsupported embedding provider: {settings.embedding_provider}."
        )
    if settings.embedding_dimension != EMBEDDING_VECTOR_DIMENSION:
        raise EmbeddingConfigurationError(
            f"EMBEDDING_DIMENSION is {settings.embedding_dimension} but the database "
            f"vector column has dimension {EMBEDDING_VECTOR_DIMENSION}."
        )
    if not settings.openai_api_key:
        raise EmbeddingConfigurationError(
            "OPENAI_API_KEY is required for the OpenAI embedding provider."
        )


def create_embedding_provider() -> OpenAIEmbeddingProvider:
    """Create the configured OpenAI provider without exposing the API key."""
    validate_embedding_configuration()

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    return OpenAIEmbeddingProvider(
        client=client,
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
    )
