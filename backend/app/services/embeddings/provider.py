from __future__ import annotations

import asyncio
import importlib.util
import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from math import isfinite
from typing import Any

from app.core.config import settings
from app.models.document_chunk import EMBEDDING_VECTOR_DIMENSION


logger = logging.getLogger("app.embeddings")

LOCAL_EMBEDDING_PROVIDER = "sentence-transformers"
SUPPORTED_EMBEDDING_PROVIDERS = frozenset({LOCAL_EMBEDDING_PROVIDER, "openai"})
# CPU inference gives the same vectors on every run and machine, so stored document
# embeddings and live query embeddings always come from identical computation.
LOCAL_EMBEDDING_DEVICE = "cpu"


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
                dimensions=self._dimension,
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


_MODEL_CACHE: dict[str, Any] = {}
_MODEL_CACHE_LOCK = threading.Lock()


def load_sentence_transformer(model_name: str) -> Any:
    """Load a sentence-transformers model once per process (downloaded on first use)."""
    with _MODEL_CACHE_LOCK:
        if model_name not in _MODEL_CACHE:
            from sentence_transformers import SentenceTransformer

            _MODEL_CACHE[model_name] = SentenceTransformer(model_name, device=LOCAL_EMBEDDING_DEVICE)
        return _MODEL_CACHE[model_name]


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Local embeddings with sentence-transformers: no API key and no per-request network.

    Loading and encoding are blocking, so both run in a worker thread. Vectors are
    L2-normalized, which leaves cosine distance unchanged.
    """

    def __init__(
        self,
        *,
        model: str,
        dimension: int,
        loader: Callable[[str], Any] = load_sentence_transformer,
        batch_size: int = 32,
    ) -> None:
        if not model.strip():
            raise ValueError("Embedding model must not be empty.")
        if dimension <= 0:
            raise ValueError("Embedding dimension must be greater than zero.")
        if batch_size <= 0:
            raise ValueError("Embedding batch size must be greater than zero.")
        self._model = model
        self._dimension = dimension
        self._loader = loader
        self._batch_size = batch_size

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
            encoder = await asyncio.to_thread(self._loader, self._model)
        except Exception as exc:
            # The model is missing, cannot be downloaded or is invalid. Text is never logged.
            logger.warning("Local embedding model could not be loaded error_type=%s", type(exc).__name__)
            raise EmbeddingProviderError("The local embedding model could not be loaded.") from exc
        try:
            raw = await asyncio.to_thread(
                encoder.encode,
                list(texts),
                batch_size=self._batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            raw_vectors = [list(vector) for vector in raw]
        except Exception as exc:
            logger.warning("Local embedding failed error_type=%s", type(exc).__name__)
            raise EmbeddingProviderError("The local embedding model could not embed the input.") from exc

        vectors = _validate_vectors(raw_vectors)
        if len(vectors) != len(texts):
            raise EmbeddingProviderError(f"Provider returned {len(vectors)} vectors for {len(texts)} inputs.")
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
    return _validate_vectors(raw_vectors)


def _validate_vectors(raw_vectors: Sequence[Sequence[Any]]) -> list[list[float]]:
    """Convert raw vectors to floats, rejecting non-numeric and non-finite values."""
    vectors: list[list[float]] = []
    for index, raw_vector in enumerate(raw_vectors):
        if not all(_is_real_number(value) for value in raw_vector):
            raise EmbeddingProviderError(f"Embedding vector {index} contains non-numeric values.")
        vector = [float(value) for value in raw_vector]
        if not all(isfinite(value) for value in vector):
            raise EmbeddingProviderError(f"Embedding vector {index} contains non-finite values.")
        vectors.append(vector)
    return vectors


def _is_real_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    # numpy scalars (float32 from local models) without importing numpy here.
    return type(value).__module__ == "numpy" and hasattr(value, "dtype") and value.dtype.kind in "fiu"


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
    if settings.embedding_provider == LOCAL_EMBEDDING_PROVIDER:
        if importlib.util.find_spec("sentence_transformers") is None:
            raise EmbeddingConfigurationError(
                "The sentence-transformers package is required for local embeddings."
            )
    elif not settings.openai_api_key:
        raise EmbeddingConfigurationError(
            "OPENAI_API_KEY is required for the OpenAI embedding provider."
        )


def create_embedding_provider() -> EmbeddingProvider:
    """Create the configured provider without loading models or exposing API keys."""
    validate_embedding_configuration()

    if settings.embedding_provider == LOCAL_EMBEDDING_PROVIDER:
        return SentenceTransformerEmbeddingProvider(
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
        )

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    return OpenAIEmbeddingProvider(
        client=client,
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
    )
