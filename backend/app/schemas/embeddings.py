from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VectorSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=20_000)
    top_k: int = Field(default=5, ge=1, le=20)


class EmbeddingStorageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    chunks_processed: int = Field(ge=1)
    embeddings_created: int = Field(ge=1)
    embedding_model: str
    status: str


class VectorSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    document_id: UUID
    chunk_index: int
    page_number: int | None
    source_locator: str | None
    content: str
    distance: float = Field(description="Cosine distance in [0, 2]; lower is closer.")
    similarity: float = Field(description="Cosine similarity, 1 - distance; higher is closer.")


class VectorSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    top_k: int
    distance_metric: Literal["cosine"] = "cosine"
    embedding_model: str
    results: list[VectorSearchResult]
