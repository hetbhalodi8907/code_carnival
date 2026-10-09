from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dependencies import require_permission
from app.core.config import settings
from app.db.session import get_session_factory
from app.schemas.pdf import ImageIngestionResult, PDFIngestionResult, PDFProcessingResult
from app.services.embeddings.storage import embed_ingested_document
from app.services.ocr.ingestion import ingest_image
from app.services.ocr.ocr import (
    ImageValidationError,
    OCREmptyError,
    OCRFailedError,
    OCRUnavailableError,
)
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
    """Validate, extract, chunk, persist and embed a PDF; the uploader receives an explicit grant.

    The uploader (and no one else) can retrieve it until further grants are added; identity comes
    only from the bearer token.
    """
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
        stored = await ingest_pdf(
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

    # Index immediately so the document is searchable (by users with a grant) without a second call.
    embedded = await embed_ingested_document(document_id=stored.document_id, session_factory=session_factory)
    return PDFIngestionResult(
        document_id=stored.document_id,
        filename=stored.filename,
        source_type=stored.source_type,
        source_path=stored.source_path,
        page_count=stored.page_count,
        chunk_count=stored.chunk_count,
        status=stored.status,
        embedding_status=embedded.status,
        embedding_model=embedded.model,
    )


@router.post(
    "/documents/ingest-image",
    response_model=ImageIngestionResult,
    status_code=201,
    responses={
        400: {"description": "Not a supported, valid PNG/JPEG image."},
        413: {"description": "The image is larger than MAX_IMAGE_SIZE_MB."},
        422: {"description": "OCR found no readable text."},
        502: {"description": "The OCR engine failed on this image."},
        503: {"description": "OCR is not installed on the server."},
    },
)
async def ingest_image_endpoint(
    file: UploadFile,
    user: AuthenticatedUser = Depends(require_document_write),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> ImageIngestionResult:
    """OCR a PNG/JPEG, chunk and embed its text; the uploader receives an explicit grant.

    Like every document, the result is retrievable only by users with an explicit grant.
    """
    limit = settings.max_image_size_mb * 1024 * 1024
    try:
        content = await file.read(limit + 1)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The image upload could not be read.") from exc
    if len(content) > limit:
        raise HTTPException(
            status_code=413, detail=f"The image must be no larger than {settings.max_image_size_mb} MB."
        )

    try:
        result = await ingest_image(
            filename=file.filename or "",
            content_type=file.content_type,
            content=content,
            session_factory=session_factory,
            owner_user_id=user.id,
        )
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OCREmptyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OCRUnavailableError as exc:
        raise HTTPException(status_code=503, detail="OCR is not available on the server.") from exc
    except OCRFailedError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except PDFIngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ImageIngestionResult(**{**asdict(result)})
