"""Request and response models for the document approval workflow.

Responses never contain filesystem paths, quarantine keys or extracted text. ``document_id`` appears only once the
document is indexed and searchable.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


SubmissionStatus = Literal["pending_approval", "indexing", "ready", "rejected", "failed"]

RejectionReason = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=300)]


class SubmitterRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    email: str


class SubmissionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    filename: str
    source_type: Literal["pdf", "image"]
    mime_type: str
    size_bytes: int
    page_count: int | None
    image_width: int | None
    image_height: int | None
    status: SubmissionStatus
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None
    rejection_reason: str | None
    failure_message: str | None = Field(description="A fixed, safe explanation of why processing failed; never a traceback.")
    attempts: int
    document_id: UUID | None = Field(description="Set only when the document is indexed and searchable (status ready).")
    preview_available: bool = Field(description="True while the quarantined file still exists and can be previewed.")
    submitter: SubmitterRef | None = Field(default=None, description="Only in the approver's queue.")


class SubmissionList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submissions: list[SubmissionOut]


class RejectRequest(BaseModel):
    """An optional short reason. Identity and permission come from the bearer token, never from this body."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: RejectionReason | None = None
