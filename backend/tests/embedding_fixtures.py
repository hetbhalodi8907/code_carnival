"""Deterministic technical fixtures for embedding and vector-search tests."""

import re
import zlib
from collections.abc import Sequence

from app.models.document_chunk import EMBEDDING_VECTOR_DIMENSION
from app.services.embeddings.provider import EmbeddingProvider


def basis(*weights: float, dimension: int = EMBEDDING_VECTOR_DIMENSION) -> list[float]:
    """Return a vector whose leading components are ``weights`` and the rest zero."""
    return [*weights, *([0.0] * (dimension - len(weights)))]


class FakeEmbeddingProvider(EmbeddingProvider):
    """Maps known texts to fixed vectors and records every provider call."""

    def __init__(
        self,
        vectors: dict[str, list[float]],
        *,
        model: str = "fake-embedding-model",
    ) -> None:
        self._vectors = vectors
        self._model = model
        self.calls: list[list[str]] = []

    @property
    def model(self) -> str:
        return self._model

    async def embed_text(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._vectors[text] for text in texts]


_TOKEN = re.compile(r"[a-z0-9]+")


def lexical_vector(text: str, dimension: int = EMBEDDING_VECTOR_DIMENSION) -> list[float]:
    """Deterministic bag-of-words vector: texts sharing words have small cosine distance."""
    vector = [0.0] * dimension
    for token in _TOKEN.findall(text.lower()):
        if len(token) > 2:
            vector[zlib.crc32(token.encode()) % dimension] += 1.0
    if not any(vector):
        vector[0] = 1.0
    return vector


class LexicalEmbeddingProvider(EmbeddingProvider):
    """Offline stand-in for a real embedding model, used for retrieval-security tests."""

    @property
    def model(self) -> str:
        return "test-lexical-embedding"

    async def embed_text(self, text: str) -> list[float]:
        return lexical_vector(text)

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [lexical_vector(text) for text in texts]
