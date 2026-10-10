"""Document approval workflow API: submit a PDF or image for CEO review, and review it.

Authorization is enforced here on every route, from the bearer token and the database (never from the request):

- submit and list my submissions : ``documents:submit`` (all six demo roles)
- queue, approve, reject         : ``documents:approve`` (SUPER_ADMIN only)
- read one submission / preview  : the submitter, or a holder of ``documents:approve``

A submission that does not exist and one the caller may not see produce the same 404. Nothing here makes a pending
file searchable: only an approval creates a document, through the existing ingestion service.
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dependencies import get_current_user, require_permission
from app.core.config import settings
from app.db.session import get_session_factory
from app.models.submission import DocumentSubmission
from app.schemas.submissions import RejectRequest, SubmissionList, SubmissionOut, SubmitterRef
from app.services.authorization import AuthenticatedUser
from app.services.submissions.service import (
    SubmissionConflict,
    SubmissionNotFound,
    SubmissionRejected,
    SubmissionService,
    TooManyPending,
)


logger = logging.getLogger("app.submissions")

router = APIRouter(prefix="/document-submissions", tags=["document-submissions"])

NOT_FOUND = "The submission was not found."
TOO_MANY = "You have too many submissions awaiting review. Wait for a decision before submitting more."


def _out(row: DocumentSubmission, submitter: tuple[str, str] | None = None) -> SubmissionOut:
    return SubmissionOut(
        id=row.id,
        filename=row.original_filename,
        source_type=row.source_type,  # type: ignore[arg-type]
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        page_count=row.page_count,
        image_width=row.image_width,
        image_height=row.image_height,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        decided_at=row.decided_at,
        rejection_reason=row.rejection_reason,
        failure_message=row.failure_message,
        attempts=row.attempts,
        document_id=row.document_id if row.status == "ready" else None,
        preview_available=row.quarantine_key is not None and row.status in ("pending_approval", "indexing", "failed"),
        submitter=SubmitterRef(name=submitter[0], email=submitter[1]) if submitter else None,
    )


def _service(session_factory: async_sessionmaker[AsyncSession]) -> SubmissionService:
    return SubmissionService(session_factory)


@router.post(
    "",
    response_model=SubmissionOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        413: {"description": "The file is larger than the configured limit."},
        422: {"description": "Not a valid PDF, PNG or JPEG (extension, type, signature, content, size, pages or pixels)."},
        429: {"description": "Too many submissions are already awaiting review."},
    },
)
async def submit_document(
    file: UploadFile,
    user: AuthenticatedUser = Depends(require_permission("documents", "submit")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> SubmissionOut:
    """Validate a PDF or image and place it in quarantine as ``pending_approval``.

    No document, chunk, embedding or grant is created: the file cannot be searched until the CEO approves it.
    """
    filename = file.filename or ""
    is_pdf = Path(filename).suffix.lower() == ".pdf"
    limit = (settings.max_pdf_size_mb if is_pdf else settings.max_image_size_mb) * 1024 * 1024
    try:
        content = await file.read(limit + 1)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The upload could not be read.") from exc
    if len(content) > limit:
        label = "PDF" if is_pdf else "image"
        raise HTTPException(status_code=413, detail=f"The {label} must be no larger than {limit // (1024 * 1024)} MB.")
    try:
        row = await _service(session_factory).submit(user, filename, file.content_type, content)
    except SubmissionRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TooManyPending:
        raise HTTPException(status_code=429, detail=TOO_MANY) from None
    return _out(row)


@router.get("/mine", response_model=SubmissionList)
async def my_submissions(
    user: AuthenticatedUser = Depends(require_permission("documents", "submit")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> SubmissionList:
    """Only the caller's own submissions."""
    rows = await _service(session_factory).list_mine(user)
    return SubmissionList(submissions=[_out(row) for row in rows])


@router.get("/queue", response_model=SubmissionList)
async def approval_queue(
    _approver: AuthenticatedUser = Depends(require_permission("documents", "approve")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> SubmissionList:
    """Submissions awaiting a decision, being indexed, or failed and retryable (approvers only)."""
    items = await _service(session_factory).queue()
    return SubmissionList(submissions=[_out(row, (name, email)) for row, name, email in items])


@router.get("/{submission_id}", response_model=SubmissionOut)
async def get_submission(
    submission_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> SubmissionOut:
    try:
        row, name, email = await _service(session_factory).get_visible(submission_id, user)
    except SubmissionNotFound:
        raise HTTPException(status_code=404, detail=NOT_FOUND) from None
    return _out(row, (name, email) if user.has_permission("documents", "approve") else None)


@router.get(
    "/{submission_id}/preview",
    responses={200: {"content": {"application/pdf": {}, "image/png": {}, "image/jpeg": {}}}, 404: {"description": NOT_FOUND}},
)
async def preview_submission(
    submission_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> Response:
    """The quarantined file, streamed through this authenticated route for its submitter or an approver.

    It is not indexed, extracted or cached, and quarantine storage is never exposed by path.
    """
    try:
        content, mime_type = await _service(session_factory).preview(submission_id, user)
    except SubmissionNotFound:
        raise HTTPException(status_code=404, detail=NOT_FOUND) from None
    extension = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}.get(mime_type, "bin")
    return Response(
        content=content,
        media_type=mime_type,
        headers={
            # A fixed name: the uploaded filename never reaches a response header.
            "Content-Disposition": f'inline; filename="submission-preview.{extension}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store, private",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.post(
    "/{submission_id}/approve",
    response_model=SubmissionOut,
    responses={
        404: {"description": NOT_FOUND},
        409: {"description": "Already being processed, or already rejected."},
    },
)
async def approve_submission(
    submission_id: UUID,
    approver: AuthenticatedUser = Depends(require_permission("documents", "approve")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> SubmissionOut:
    """Approve a submission and run the existing ingestion, extraction/OCR, chunking and indexing.

    The response is the submission's resulting state: ``ready`` (searchable by its submitter under the existing
    grant), or ``failed`` with a safe message and a retry path (call this route again). Repeating a successful
    approval changes nothing. Retrying a failed one is the supported way to recover.
    """
    try:
        row = await _service(session_factory).approve(submission_id, approver)
    except SubmissionNotFound:
        raise HTTPException(status_code=404, detail=NOT_FOUND) from None
    except SubmissionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return _out(row)


@router.post(
    "/{submission_id}/reject",
    response_model=SubmissionOut,
    responses={404: {"description": NOT_FOUND}, 409: {"description": "Already indexing or indexed."}},
)
async def reject_submission(
    submission_id: UUID,
    body: RejectRequest | None = None,
    approver: AuthenticatedUser = Depends(require_permission("documents", "approve")),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> SubmissionOut:
    """Reject a submission: its quarantined file is deleted and no document is ever created."""
    try:
        row = await _service(session_factory).reject(submission_id, approver, body.reason if body else None)
    except SubmissionNotFound:
        raise HTTPException(status_code=404, detail=NOT_FOUND) from None
    except SubmissionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return _out(row)
