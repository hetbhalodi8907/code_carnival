from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models import Document, DocumentChunk, DocumentUserAccess
from app.services.pdf.chunker import chunk_pdf_pages
from app.services.pdf.extractor import PDFExtractionError, extract_pdf_pages
from app.services.pdf.validator import PDFValidationError, validate_pdf_upload


class PDFIngestionError(RuntimeError):
    """Raised when a PDF cannot be persisted safely."""


class PDFIngestionResult:
    """Structured outcome returned after a successful PDF ingestion."""

    def __init__(
        self,
        document_id: UUID,
        filename: str,
        source_path: str,
        page_count: int,
        chunk_count: int,
        status: str,
        source_type: str = "pdf",
    ) -> None:
        self.document_id = document_id
        self.filename = filename
        self.source_path = source_path
        self.page_count = page_count
        self.chunk_count = chunk_count
        self.status = status
        self.source_type = source_type


async def ingest_pdf(
    *,
    filename: str,
    content_type: str | None,
    content: bytes,
    chunk_size: int,
    chunk_overlap: int,
    session_factory: async_sessionmaker[AsyncSession],
    document_id: UUID | None = None,
    owner_user_id: UUID | None = None,
) -> PDFIngestionResult:
    """Validate, extract, chunk, and persist a PDF in one database transaction.

    ``document_id`` lets callers such as the demo dataset generator use a
    deterministic identifier; a new random identifier is used when it is omitted.
    ``owner_user_id`` records the uploader as owner and grants them explicit
    document_user_access in the same transaction (access is default deny).
    """
    try:
        validate_pdf_upload(filename, content_type, content)
        extraction = extract_pdf_pages(content)
        chunks = chunk_pdf_pages(
            extraction,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    except (PDFValidationError, PDFExtractionError, ValueError) as exc:
        raise PDFIngestionError(str(exc)) from exc

    return await persist_document(
        filename=filename,
        content=content,
        extension=".pdf",
        source_type="pdf",
        mime_type="application/pdf",
        chunks=chunks,
        page_count=int(extraction["page_count"]),
        session_factory=session_factory,
        document_id=document_id,
        owner_user_id=owner_user_id,
    )


async def persist_document(
    *,
    filename: str,
    content: bytes,
    extension: str,
    source_type: str,
    mime_type: str,
    chunks: list[dict[str, object]],
    page_count: int,
    session_factory: async_sessionmaker[AsyncSession],
    document_id: UUID | None = None,
    owner_user_id: UUID | None = None,
) -> PDFIngestionResult:
    """Store the original file and persist the document and its chunks in one transaction.

    Shared by PDF and image (OCR) ingestion. Access is default deny: the only grant created
    is the uploader's own (``owner_user_id``), in the same transaction.
    """
    if document_id is None:
        document_id = uuid4()
    source_path = f"{document_id}{extension}"
    storage_path = Path(settings.document_storage_path)
    storage_path.mkdir(parents=True, exist_ok=True)
    destination = storage_path / source_path
    if destination.exists():
        # Never overwrite (or, on rollback, delete) a file owned by another document.
        raise PDFIngestionError("A stored file already exists for this document identifier.")

    try:
        destination.write_bytes(content)
    except OSError as exc:
        raise PDFIngestionError("The file could not be stored.") from exc

    session = session_factory()
    try:
        document = Document(
            id=document_id,
            title=filename,
            source_type=source_type,
            source_path=source_path,
            mime_type=mime_type,
            status="processed",
            owner_user_id=owner_user_id,
        )
        session.add(document)
        await session.flush()
        if owner_user_id is not None:
            session.add(DocumentUserAccess(document_id=document_id, user_id=owner_user_id))

        session.add_all(
            DocumentChunk(
                document_id=document_id,
                chunk_index=chunk["chunk_index"],
                content=chunk["content"],
                page_number=chunk["page_number"],
                source_locator=chunk["source_locator"],
                chunk_metadata=chunk["metadata"],
            )
            for chunk in chunks
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise PDFIngestionError("The ingestion transaction failed.") from exc
    finally:
        await session.close()

    return PDFIngestionResult(
        document_id=document_id,
        filename=filename,
        source_path=source_path,
        page_count=page_count,
        chunk_count=len(chunks),
        status="processed",
        source_type=source_type,
    )
