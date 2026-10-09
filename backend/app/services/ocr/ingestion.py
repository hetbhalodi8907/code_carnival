"""Image OCR ingestion: validate -> OCR -> chunk -> persist -> embed (Part 9).

Reuses the PDF pipeline's chunker, transactional persistence (including the uploader's
explicit grant, so access stays default deny) and the configured embedding service.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.services.embeddings.service import EmbeddingService
from app.services.embeddings.storage import EmbeddingOutcome, embed_ingested_document
from app.services.ocr.ocr import OCREngine, extract_image_text, ocr_to_extraction, validate_image_upload
from app.services.pdf.chunker import chunk_pdf_pages
from app.services.pdf.ingestion import persist_document


logger = logging.getLogger("app.ocr")

@dataclass(frozen=True)
class ImageIngestionResult:
    document_id: UUID
    filename: str
    source_path: str
    chunk_count: int
    ocr_line_count: int
    ocr_mean_confidence: float
    embedding_status: EmbeddingOutcome


async def ingest_image(
    *,
    filename: str,
    content_type: str | None,
    content: bytes,
    session_factory: async_sessionmaker[AsyncSession],
    owner_user_id: UUID | None,
    embedding_service: EmbeddingService | None = None,
    engine: OCREngine | None = None,
    document_id: UUID | None = None,
) -> ImageIngestionResult:
    """Ingest one image. Raises the OCR/validation/ingestion errors defined in their modules.

    ``embedding_service=None`` means "build the configured one"; a missing or failing
    embedding provider leaves the document stored but not yet searchable and is reported
    as ``embedding_status`` rather than failing the upload.
    """
    mime_type = validate_image_upload(filename, content_type, content)
    # OCR is CPU-bound and blocking.
    ocr = await asyncio.to_thread(extract_image_text, content, engine)
    chunks = chunk_pdf_pages(
        ocr_to_extraction(ocr), chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
    )
    for chunk in chunks:
        # An image has no pages: label it by source type instead of "page 1".
        chunk["page_number"] = None
        chunk["source_locator"] = "image:ocr"
        chunk["metadata"] = {
            "source_type": "image",
            "chunk_index": chunk["chunk_index"],
            "ocr_engine": ocr.engine,
            "ocr_mean_confidence": ocr.mean_confidence,
            "ocr_line_count": ocr.line_count,
        }
    suffix = "." + filename.rsplit(".", 1)[-1].lower()
    stored = await persist_document(
        filename=filename,
        content=content,
        extension=suffix,
        source_type="image",
        mime_type=mime_type,
        chunks=chunks,
        page_count=1,
        session_factory=session_factory,
        document_id=document_id,
        owner_user_id=owner_user_id,
    )

    embedded = await embed_ingested_document(
        document_id=stored.document_id, session_factory=session_factory, service=embedding_service
    )

    return ImageIngestionResult(
        document_id=stored.document_id,
        filename=filename,
        source_path=stored.source_path,
        chunk_count=stored.chunk_count,
        ocr_line_count=ocr.line_count,
        ocr_mean_confidence=ocr.mean_confidence,
        embedding_status=embedded.status,
    )
