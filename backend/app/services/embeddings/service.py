from __future__ import annotations

from collections.abc import Sequence
from math import isfinite

from app.core.config import settings
from app.services.embeddings.provider import EmbeddingProvider, create_embedding_provider


class EmbeddingServiceError(RuntimeError):
    """Raised when embedding generation or validation fails."""


class EmbeddingService:
    """Batch provider calls, validate provider output, and enforce the vector dimension."""

    def __init__(
        self,
        provider: EmbeddingProvider,
        *,
        dimension: int,
        batch_size: int = 100,
    ) -> None:
        if dimension <= 0:
            raise ValueError("Embedding dimension must be greater than zero.")
        if batch_size <= 0:
            raise ValueError("Embedding batch size must be greater than zero.")
        self._provider = provider
        self._dimension = dimension
        self._batch_size = batch_size

    @property
    def model(self) -> str:
        return self._provider.model

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_text(self, text: str) -> list[float]:
        vector = await self._provider.embed_text(text)
        return self._validate_vector(vector)

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            raise EmbeddingServiceError("At least one text value is required.")

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            batch_vectors = await self._provider.embed_texts(batch)
            if len(batch_vectors) != len(batch):
                raise EmbeddingServiceError(
                    f"Provider returned {len(batch_vectors)} vectors for {len(batch)} inputs."
                )
            vectors.extend(self._validate_vector(vector) for vector in batch_vectors)
        return vectors

    def _validate_vector(self, vector: Sequence[float]) -> list[float]:
        if len(vector) != self._dimension:
            raise EmbeddingServiceError(
                f"Embedding vector has length {len(vector)}; expected {self._dimension}."
            )
        if not all(isfinite(value) for value in vector):
            raise EmbeddingServiceError("Embedding vector contains non-finite values.")
        return list(vector)


def create_embedding_service() -> EmbeddingService:
    """Build the embedding service from centralized settings."""
    return EmbeddingService(
        create_embedding_provider(),
        dimension=settings.embedding_dimension,
        batch_size=settings.embedding_batch_size,
    )
