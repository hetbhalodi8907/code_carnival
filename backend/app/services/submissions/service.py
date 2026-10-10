"""The CEO approval workflow: submit -> (approve | reject) -> ingest through the EXISTING pipeline.

Invariants (each is covered by tests):

- A submission is not a document. While it is pending, rejected or failed there is no ``documents`` row, no chunk, no
  embedding and no access grant, so no retrieval query can reach it. Its file is in quarantine storage.
- Only approval creates an active document, and only by calling the existing ``ingest_pdf`` / ``ingest_image`` and
  embedding code. The document is owned by, and granted only to, the submitter (the existing uploader-only policy);
  approving does not widen access.
- One approval wins: the submission row is locked (``SELECT ... FOR UPDATE``) and moved to ``indexing`` in a committed
  transaction, so concurrent or repeated approvals cannot ingest the same file twice. A submission that is already
  ``ready`` answers a repeat approval with its current state.
- A failed attempt removes exactly the document ID reserved for that attempt (and its chunks and grant, by cascade)
  and its stored copy, keeps the quarantine file and the submission, and records a fixed, safe message so the
  approver can retry. A crashed attempt is cleaned the same way before the next one starts.
- Only provider-independent checks run here. No model is involved in a decision and pending content never reaches one.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import models
from app.core.config import settings
from app.services.authorization import AuthenticatedUser
from app.services.embeddings.storage import embed_ingested_document
from app.services.ocr.ingestion import ingest_image
from app.services.ocr.ocr import (
    ImageValidationError,
    OCREmptyError,
    OCRFailedError,
    OCRUnavailableError,
    validate_image_upload,
)
from app.services.pdf.extractor import PDFExtractionError, extract_pdf_pages
from app.services.pdf.ingestion import NO_TEXT_MESSAGE, PDFIngestionError, display_name, ingest_pdf
from app.services.pdf.validator import PDFValidationError, validate_pdf_upload
from app.services.submissions import storage


logger = logging.getLogger("app.submissions")

PENDING, INDEXING, READY, REJECTED, FAILED = "pending_approval", "indexing", "ready", "rejected", "failed"
QUEUE_STATUSES = (PENDING, INDEXING, FAILED)

_FAILURES = {
    "embedding_failed": "The document's text could not be indexed. Try again.",
    "embedding_not_configured": "Indexing is not configured on the server.",
    "ocr_no_text": "OCR found no readable text in the image.",
    "ocr_unavailable": "OCR is not available on the server.",
    "ocr_failed": "The OCR engine failed on this image.",
    "file_missing": "The quarantined file is no longer available. Reject this submission.",
    "unexpected": "Processing failed unexpectedly. Try again.",
}


class SubmissionRejected(ValueError):
    """The upload is not an acceptable PDF or image. The message is safe to show."""


class SubmissionNotFound(LookupError):
    """No such submission, or the caller may not see it (the two are indistinguishable)."""


class SubmissionConflict(RuntimeError):
    """The submission is not in a state that allows the requested action."""


class TooManyPending(RuntimeError):
    """The user already has the maximum number of submissions awaiting review."""


@dataclass(frozen=True)
class ValidatedFile:
    source_type: str  # "pdf" | "image"
    mime_type: str
    extension: str
    size_bytes: int
    page_count: int | None
    image_width: int | None
    image_height: int | None


def validate_submission(filename: str, content_type: str | None, content: bytes) -> ValidatedFile:
    """The existing PDF and image validators, applied before anything is stored. Raises ``SubmissionRejected``."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        try:
            validate_pdf_upload(filename, content_type, content)
            extraction = extract_pdf_pages(content)
        except (PDFValidationError, PDFExtractionError) as exc:
            raise SubmissionRejected(str(exc)) from exc
        if not extraction["has_extractable_text"]:
            raise SubmissionRejected(NO_TEXT_MESSAGE)
        return ValidatedFile("pdf", "application/pdf", ".pdf", len(content), int(extraction["page_count"]), None, None)
    if suffix in {".png", ".jpg", ".jpeg"}:
        try:
            mime = validate_image_upload(filename, content_type, content)
        except ImageValidationError as exc:
            raise SubmissionRejected(str(exc)) from exc
        from PIL import Image

        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
        return ValidatedFile("image", mime, storage.EXTENSIONS[mime], len(content), None, width, height)
    raise SubmissionRejected("Only PDF, PNG and JPEG files can be submitted.")


def _now() -> datetime:
    return datetime.now(UTC)


class SubmissionService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ---- submit ------------------------------------------------------------------------------------------

    async def submit(
        self, user: AuthenticatedUser, filename: str, content_type: str | None, content: bytes
    ) -> models.DocumentSubmission:
        """Validate, quarantine and record a submission as ``pending_approval``. Creates no document."""
        validated = validate_submission(filename, content_type, content)
        async with self._session_factory() as session:
            waiting = await session.scalar(
                select(func.count())
                .select_from(models.DocumentSubmission)
                .where(models.DocumentSubmission.submitter_user_id == user.id, models.DocumentSubmission.status == PENDING)
            )
        if (waiting or 0) >= settings.max_pending_submissions_per_user:
            raise TooManyPending("Too many submissions are awaiting review.")

        submission_id = uuid4()
        key = storage.make_key(submission_id, validated.extension)
        storage.write(key, content)
        try:
            async with self._session_factory() as session:
                row = models.DocumentSubmission(
                    id=submission_id,
                    submitter_user_id=user.id,
                    original_filename=display_name(filename),
                    source_type=validated.source_type,
                    mime_type=validated.mime_type,
                    size_bytes=validated.size_bytes,
                    page_count=validated.page_count,
                    image_width=validated.image_width,
                    image_height=validated.image_height,
                    quarantine_key=key,
                    status=PENDING,
                    attempts=0,
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
        except Exception:
            storage.delete(key)  # nothing is recorded, so nothing may stay on disk
            raise
        logger.info("Submission received submission_id=%s user_id=%s type=%s", row.id, user.id, row.source_type)
        return row

    # ---- reading -------------------------------------------------------------------------------------------

    async def list_mine(self, user: AuthenticatedUser) -> list[models.DocumentSubmission]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(models.DocumentSubmission)
                .where(models.DocumentSubmission.submitter_user_id == user.id)
                .order_by(models.DocumentSubmission.created_at.desc())
                .limit(100)
            )
            return list(rows)

    async def queue(self) -> list[tuple[models.DocumentSubmission, str, str]]:
        """Submissions that still need the approver (pending, being indexed, or failed), oldest first."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(models.DocumentSubmission, models.User.full_name, models.User.email)
                .join(models.User, models.User.id == models.DocumentSubmission.submitter_user_id)
                .where(models.DocumentSubmission.status.in_(QUEUE_STATUSES))
                .order_by(models.DocumentSubmission.created_at)
                .limit(200)
            )
            return [(row, name, email) for row, name, email in result.all()]

    async def get_visible(
        self, submission_id: UUID, user: AuthenticatedUser
    ) -> tuple[models.DocumentSubmission, str, str]:
        """The submission, if it is the caller's own or the caller may approve. Otherwise it does not exist."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(models.DocumentSubmission, models.User.full_name, models.User.email)
                .join(models.User, models.User.id == models.DocumentSubmission.submitter_user_id)
                .where(models.DocumentSubmission.id == submission_id)
            )
            found = result.first()
        if found is None:
            raise SubmissionNotFound
        row, name, email = found
        if row.submitter_user_id != user.id and not user.has_permission("documents", "approve"):
            raise SubmissionNotFound
        return row, name, email

    async def preview(self, submission_id: UUID, user: AuthenticatedUser) -> tuple[bytes, str]:
        """The quarantined file for the submitter or an approver; gone once it was ingested or rejected."""
        row, _, _ = await self.get_visible(submission_id, user)
        if row.quarantine_key is None or row.status in (READY, REJECTED):
            raise SubmissionNotFound
        limit = (settings.max_pdf_size_mb if row.source_type == "pdf" else settings.max_image_size_mb) * 1024 * 1024
        try:
            return storage.read(row.quarantine_key, limit=limit), row.mime_type
        except storage.QuarantineError:
            raise SubmissionNotFound from None

    # ---- reject ----------------------------------------------------------------------------------------------

    async def reject(self, submission_id: UUID, approver: AuthenticatedUser, reason: str | None) -> models.DocumentSubmission:
        """Record the decision and delete the quarantined file. Creates no document, chunk, embedding or grant."""
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    select(models.DocumentSubmission).where(models.DocumentSubmission.id == submission_id).with_for_update()
                )
                if row is None:
                    raise SubmissionNotFound
                if row.status == REJECTED:
                    return row  # a repeat is harmless
                if row.status not in (PENDING, FAILED):
                    raise SubmissionConflict("This submission can no longer be rejected.")
                key, previous_attempt = row.quarantine_key, row.attempt_document_id
                row.status = REJECTED
                row.decided_by_user_id = approver.id
                row.decided_at = _now()
                row.rejection_reason = reason
                row.failure_code = row.failure_message = None
                row.quarantine_key = None
                row.attempt_document_id = None
        # Outside the transaction: a failed attempt may have left a partial document; remove exactly that one.
        if previous_attempt is not None:
            await self._discard_document(previous_attempt)
        if key is not None and not storage.delete(key):
            logger.warning("Quarantined file could not be removed submission_id=%s", submission_id)
        logger.info("Submission rejected submission_id=%s approver_id=%s", submission_id, approver.id)
        return await self._load(submission_id)

    # ---- approve ----------------------------------------------------------------------------------------------

    async def approve(self, submission_id: UUID, approver: AuthenticatedUser) -> models.DocumentSubmission:
        """Claim the submission and run the existing ingestion. Safe to call again (retry, double click, race)."""
        now = _now()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    select(models.DocumentSubmission).where(models.DocumentSubmission.id == submission_id).with_for_update()
                )
                if row is None:
                    raise SubmissionNotFound
                if row.status == READY:
                    return row  # idempotent: already approved and indexed, nothing is created again
                stale = row.updated_at < now - timedelta(minutes=settings.submission_stale_minutes)
                if row.status == REJECTED:
                    raise SubmissionConflict("This submission was rejected.")
                if row.status == INDEXING and not stale:
                    raise SubmissionConflict("This submission is already being processed.")
                if row.status not in (PENDING, FAILED, INDEXING):
                    raise SubmissionConflict("This submission cannot be approved.")
                previous_attempt = row.attempt_document_id
                attempt_id = uuid4()
                row.status = INDEXING
                row.decided_by_user_id = approver.id
                row.decided_at = now
                row.failure_code = row.failure_message = None
                row.attempt_document_id = attempt_id
                row.attempts = row.attempts + 1
                key, source_type, mime = row.quarantine_key, row.source_type, row.mime_type
                filename, submitter_id = row.original_filename, row.submitter_user_id
        logger.info("Submission approved submission_id=%s approver_id=%s attempt=%s", submission_id, approver.id, attempt_id)

        if previous_attempt is not None:
            await self._discard_document(previous_attempt)  # a crashed or failed earlier attempt, by exact ID

        try:
            if key is None:
                await self._fail(submission_id, attempt_id, "file_missing")
                return await self._load(submission_id)
            limit = (settings.max_pdf_size_mb if source_type == "pdf" else settings.max_image_size_mb) * 1024 * 1024
            try:
                content = storage.read(key, limit=limit)
            except storage.QuarantineError:
                await self._fail(submission_id, attempt_id, "file_missing")
                return await self._load(submission_id)
            code, message = await self._ingest(source_type, filename, mime, content, submitter_id, attempt_id)
            if code is not None:
                await self._discard_document(attempt_id)
                await self._fail(submission_id, attempt_id, code, message)
                return await self._load(submission_id)
            if not await self._finish(submission_id, attempt_id):
                await self._discard_document(attempt_id)
                await self._fail(submission_id, attempt_id, "unexpected")
                return await self._load(submission_id)
        except Exception as exc:  # noqa: BLE001 - nothing may leave a half-made document behind
            logger.error("Approval failed unexpectedly submission_id=%s error_type=%s", submission_id, type(exc).__name__)
            await self._discard_document(attempt_id)
            await self._fail(submission_id, attempt_id, "unexpected")
            return await self._load(submission_id)

        # Indexed and recorded: the quarantined copy is no longer needed.
        if not storage.delete(key):
            logger.warning("Quarantined file could not be removed submission_id=%s", submission_id)
        async with self._session_factory() as session:
            await session.execute(
                update(models.DocumentSubmission).where(models.DocumentSubmission.id == submission_id).values(quarantine_key=None)
            )
            await session.commit()
        return await self._load(submission_id)

    # ---- internals -------------------------------------------------------------------------------------------

    async def _ingest(
        self, source_type: str, filename: str, mime: str, content: bytes, owner: UUID, document_id: UUID
    ) -> tuple[str | None, str | None]:
        """Run the existing ingestion + embedding. Returns (None, None) on success, else a failure code and message."""
        try:
            if source_type == "pdf":
                await ingest_pdf(
                    filename=filename, content_type=mime, content=content, chunk_size=settings.chunk_size,
                    chunk_overlap=settings.chunk_overlap, session_factory=self._session_factory,
                    document_id=document_id, owner_user_id=owner,
                )
                embedding = (await embed_ingested_document(document_id=document_id, session_factory=self._session_factory)).status
            else:
                result = await ingest_image(
                    filename=filename, content_type=mime, content=content, session_factory=self._session_factory,
                    owner_user_id=owner, document_id=document_id,
                )
                embedding = result.embedding_status
        except PDFIngestionError as exc:
            return "ingestion_failed", str(exc)[:300]
        except ImageValidationError as exc:
            return "invalid_file", str(exc)[:300]
        except OCREmptyError:
            return "ocr_no_text", _FAILURES["ocr_no_text"]
        except OCRUnavailableError:
            return "ocr_unavailable", _FAILURES["ocr_unavailable"]
        except OCRFailedError:
            return "ocr_failed", _FAILURES["ocr_failed"]
        if embedding != "completed":
            # Stored but not searchable is not "ready": the attempt is undone so nothing half-made remains.
            code = "embedding_not_configured" if embedding == "not_configured" else "embedding_failed"
            return code, _FAILURES[code]
        return None, None

    async def _discard_document(self, document_id: UUID) -> None:
        """Remove exactly one document (chunks and grants cascade) and its stored copy. Nothing else is touched."""
        async with self._session_factory() as session:
            source_path = await session.scalar(select(models.Document.source_path).where(models.Document.id == document_id))
            await session.execute(delete(models.Document).where(models.Document.id == document_id))
            await session.commit()
        if source_path and Path(source_path).name == source_path and source_path.startswith(str(document_id)):
            try:
                (Path(settings.document_storage_path) / source_path).unlink(missing_ok=True)
            except OSError:
                logger.warning("Stored copy could not be removed document_id=%s", document_id)

    async def _finish(self, submission_id: UUID, attempt_id: UUID) -> bool:
        """Mark ready, but only if this attempt still owns the submission."""
        async with self._session_factory() as session:
            result = await session.execute(
                update(models.DocumentSubmission)
                .where(
                    models.DocumentSubmission.id == submission_id,
                    models.DocumentSubmission.status == INDEXING,
                    models.DocumentSubmission.attempt_document_id == attempt_id,
                )
                .values(status=READY, document_id=attempt_id, failure_code=None, failure_message=None, updated_at=_now())
            )
            await session.commit()
            return result.rowcount == 1

    async def _fail(self, submission_id: UUID, attempt_id: UUID, code: str, message: str | None = None) -> None:
        """Record a failed attempt (the quarantine file and the submission stay, so the approver can retry)."""
        async with self._session_factory() as session:
            await session.execute(
                update(models.DocumentSubmission)
                .where(models.DocumentSubmission.id == submission_id, models.DocumentSubmission.attempt_document_id == attempt_id)
                .values(
                    status=FAILED,
                    attempt_document_id=None,
                    failure_code=code[:40],
                    failure_message=(message or _FAILURES.get(code) or _FAILURES["unexpected"])[:300],
                    updated_at=_now(),
                )
            )
            await session.commit()
        logger.warning("Submission failed submission_id=%s code=%s", submission_id, code)

    async def _load(self, submission_id: UUID) -> models.DocumentSubmission:
        async with self._session_factory() as session:
            row = await session.get(models.DocumentSubmission, submission_id)
        if row is None:
            raise SubmissionNotFound
        return row
