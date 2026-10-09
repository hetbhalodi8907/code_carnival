from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dependencies import require_permission
from app.core.config import settings
from app.db.session import get_session_factory
from app.schemas.pdf import PDFIngestionResult, PDFProcessingResult
from app.services.pdf.extractor import PDFExtractionError, extract_pdf_pages
from app.services.pdf.ingestion import PDFIngestionError, ingest_pdf
from app.services.authorization import AuthenticatedUser
from app.services.pdf.validator import PDFValidationError, validate_pdf_upload


router = APIRouter()

# Previewing and ingesting are both steps of the document upload workflow.
require_document_write = require_permission("documents", "write")


@router.post(
    "/documents/preview",
    response_model=PDFProcessingResult,
    status_code=200,
)
async def preview_pdf(
    file: UploadFile,
    _user: AuthenticatedUser = Depends(require_document_write),
) -> PDFProcessingResult:
    """Validate, extract, and clean a PDF without persisting the file."""
    filename = file.filename or ""

    try:
        content = await file.read(settings.max_pdf_size_mb * 1024 * 1024 + 1)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The PDF upload could not be read.") from exc

    if len(content) > settings.max_pdf_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"The PDF must be no larger than {settings.max_pdf_size_mb} MB.",
        )

    try:
        validate_pdf_upload(filename, file.content_type, content)
        extraction = extract_pdf_pages(content)
    except PDFValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PDFExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return PDFProcessingResult(
        filename=filename,
        page_count=extraction["page_count"],
        pages=extraction["pages"],
        text=extraction["text"],
        has_extractable_text=extraction["has_extractable_text"],
    )


@router.post(
    "/documents/ingest",
    response_model=PDFIngestionResult,
    status_code=201,
)
async def ingest_pdf_endpoint(
    file: UploadFile,
    user: AuthenticatedUser = Depends(require_document_write),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> PDFIngestionResult:
    """Validate, extract, chunk, and persist a PDF; the uploader receives an explicit grant."""
    filename = file.filename or ""

    try:
        content = await file.read(settings.max_pdf_size_mb * 1024 * 1024 + 1)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The PDF upload could not be read.") from exc

    if len(content) > settings.max_pdf_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"The PDF must be no larger than {settings.max_pdf_size_mb} MB.",
        )

    try:
        return await ingest_pdf(
            filename=filename,
            content_type=file.content_type,
            content=content,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            session_factory=session_factory,
            owner_user_id=user.id,
        )
    except PDFIngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
