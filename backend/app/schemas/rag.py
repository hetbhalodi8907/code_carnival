"""Request and response models for retrieval-augmented generation (Part 6).

``RagQuery`` is the single validation point for a question before secure retrieval.
It carries no identity: the user always comes from the validated bearer token, and
unknown fields such as ``user_id`` or ``role`` are rejected.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.services.vector_search import VectorSearchService


# A question, not a document: long enough for detailed questions, short enough to embed
# and to place in a prompt next to the authorized context.
MAX_QUERY_LENGTH = 2_000
DEFAULT_TOP_K = 5

QueryText = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=MAX_QUERY_LENGTH),
]


class RagQuery(BaseModel):
    """A user question: surrounding whitespace is trimmed and nothing else is changed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: QueryText
    # Same bounds as secure vector search, which enforces them again.
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=VectorSearchService.MAX_TOP_K, strict=True)


class AssistantSource(BaseModel):
    """An authorized passage the server retrieved and gave the model as evidence.

    Built from the server's retrieval context, never from the model's answer. It is
    evidence that was available, not a validated citation (citation validation is Part 7).
    """

    model_config = ConfigDict(extra="forbid")

    source_number: int = Field(ge=1, description="Matches SOURCE n in the model's context and [S<n>] in the answer.")
    document_id: UUID
    document_title: str
    chunk_id: UUID
    page_number: int | None
    source_locator: str | None
    similarity: float = Field(
        description="Cosine similarity for document passages; 1.0 for an exact structured-data record."
    )
    source_type: Literal["pdf", "image", "structured"] = Field(
        default="pdf",
        description="pdf: PDF text. image: text read by OCR. structured: a database record.",
    )
    cited: bool = Field(
        default=False,
        description="True when the answer cites this source with a marker that matches it. "
        "The citation proves the source was retrieved and authorized, not that it supports the sentence.",
    )


class AssistantQueryResponse(BaseModel):
    """Answer to an assistant query, with the authorized sources it was based on."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["answered", "insufficient_context", "no_authorized_context", "access_denied"] = Field(
        description=(
            "answered: grounded answer from authorized sources. insufficient_context: the authorized "
            "sources do not answer the question. no_authorized_context: no authorized source was found "
            "(the language model was not called). access_denied: the question targets information the "
            "user is not permitted to read; the server established this itself (never the language "
            "model), `sources` is empty and nothing about the restricted material is returned."
        )
    )
    answer: str = Field(description="User-facing answer, or a fixed message when there is no answer.")
    request_id: str = Field(description="Correlation ID, also returned in the X-Request-ID header.")
    sources: list[AssistantSource] = Field(
        description="Authorized passages given to the model, in ranking order. Empty unless status is answered."
    )
    unverified_source_numbers: list[int] = Field(
        description=(
            "Source numbers the answer cites as [S<n>] that match a source retrieved for this request "
            "(so they point at an authorized source), in order of first use. Whether the source supports "
            "the sentence is NOT verified, hence the name."
        )
    )
    rejected_source_numbers: list[int] = Field(
        default_factory=list,
        description="Numbers the model cited that match no retrieved source. They are removed from the answer.",
    )
    citation_check: Literal["passed", "partial", "none", "not_applicable"] = Field(
        default="not_applicable",
        description="passed: every marker matched a retrieved source. partial: some markers or identifiers "
        "were removed. none: the answer cites no retrieved source. not_applicable: no model answer.",
    )
