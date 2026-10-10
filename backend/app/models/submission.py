"""A file submitted for CEO approval, before it is (or if it never becomes) an active document.

A submission is NOT a document: while it is pending, rejected or failed there is no ``documents`` row, no chunks, no
embeddings and no access grant for it, so no retrieval query can ever reach it. Its file lives in quarantine storage
(``settings.quarantine_storage_path``), addressed only by the server-generated ``quarantine_key``.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


SUBMISSION_STATUSES = ("pending_approval", "indexing", "ready", "rejected", "failed")
SUBMISSION_SOURCE_TYPES = ("pdf", "image")


class DocumentSubmission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "document_submissions"

    submitter_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # A generated file name inside the quarantine directory; NULL once the file has been deleted.
    quarantine_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending_approval")
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Set only when ingestion finished and the document is searchable.
    document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    # The ID reserved for the document an approval attempt creates. No foreign key: it names a row that may not exist
    # (yet, or after a cleanup), so a crashed attempt can always be cleaned up by exact ID before the next one.
    attempt_document_id: Mapped[UUID | None] = mapped_column(nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_approval', 'indexing', 'ready', 'rejected', 'failed')", name="ck_document_submissions_status"
        ),
        CheckConstraint("source_type IN ('pdf', 'image')", name="ck_document_submissions_source_type"),
        Index("ix_document_submissions_status_created", "status", "created_at"),
    )
