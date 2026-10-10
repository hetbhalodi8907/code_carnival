"""Request and response models for retrieval-augmented generation (Part 6).

``RagQuery`` is the single validation point for a question before secure retrieval.
It carries no identity: the user always comes from the validated bearer token, and
unknown fields such as ``user_id`` or ``role`` are rejected.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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


# Document chat: earlier turns are context for follow-ups, never evidence, so they are small and bounded.
MAX_HISTORY_TURNS = 10
MAX_HISTORY_TURN_LENGTH = 4_000
MAX_HISTORY_TOTAL_LENGTH = 16_000
DOCUMENT_CHAT_TOP_K = 6

HistoryText = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=MAX_HISTORY_TURN_LENGTH),
]


class ChatTurn(BaseModel):
    """One earlier turn. Only user and assistant turns exist: a client cannot supply a system message."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["user", "assistant"]
    content: HistoryText


class DocumentQuery(BaseModel):
    """A question about ONE document, with the recent turns of the same session.

    It carries no identity or permission: the user comes from the bearer token, and the server decides
    whether that user may read ``document_id``. Unknown fields are rejected.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: UUID
    query: QueryText
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)

    @model_validator(mode="after")
    def _bounded_history(self) -> "DocumentQuery":
        if sum(len(turn.content) for turn in self.history) > MAX_HISTORY_TOTAL_LENGTH:
            raise ValueError("The conversation history is too long.")
        return self


class TrustProof(BaseModel):
    """What the server can substantiate about one generated answer. Present only for status "answered".

    It holds no prompt, completion, passage text or hidden-source metadata. A validated citation
    shows that a cited source was retrieved for this user; it does not prove the statement is correct.
    """

    model_config = ConfigDict(extra="forbid")

    authorization: Literal["access_controlled_retrieval"] = Field(
        description=(
            "Set only after the server confirmed this answer's context was built by the authorization-aware "
            "retrieval for the authenticated user and the model was called with exactly that context."
        )
    )
    authorized_source_count: int = Field(
        ge=0, description="Number of final sources returned to the user in `sources` (never hidden results)."
    )
    provider: str | None = Field(
        default=None, description="Provider that produced the answer after any fallback (groq, lm_studio); null if unknown."
    )
    model: str | None = Field(default=None, description="Model that produced the answer; null if unknown.")


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
    trust_proof: TrustProof | None = Field(
        default=None,
        description="Verifiable receipt for an answered query. Null for every other status (including access_denied).",
    )
