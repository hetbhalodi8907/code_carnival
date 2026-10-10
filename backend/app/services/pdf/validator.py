from __future__ import annotations

from pathlib import Path
from typing import Protocol

from fitz import FileDataError, open

from app.core.config import settings


class PDFDocument(Protocol):
    """Minimal protocol implemented by PyMuPDF documents."""

    def page_count(self) -> int: ...


MAX_FILENAME_LENGTH = 255


class PDFValidationError(ValueError):
    """Raised when an uploaded file is not safe or valid PDF input."""


def validate_pdf_upload(filename: str, content_type: str | None, content: bytes) -> None:
    """Validate a filename, MIME hint, size, and actual PDF structure."""
    if not filename.strip():
        raise PDFValidationError("A PDF filename is required.")

    if len(filename) > MAX_FILENAME_LENGTH:
        raise PDFValidationError(f"The PDF filename must be at most {MAX_FILENAME_LENGTH} characters.")

    if Path(filename).suffix.lower() != ".pdf":
        raise PDFValidationError("Only PDF files are supported.")

    if content_type is not None and content_type.lower() not in {
        "application/pdf",
        "application/x-pdf",
    }:
        raise PDFValidationError("The uploaded file is not a PDF.")

    if not content:
        raise PDFValidationError("The uploaded PDF is empty.")

    if len(content) > settings.max_pdf_size_mb * 1024 * 1024:
        raise PDFValidationError(
            f"The PDF must be no larger than {settings.max_pdf_size_mb} MB."
        )

    try:
        document = open(stream=content, filetype="pdf")
    except (FileDataError, OSError, ValueError) as exc:
        raise PDFValidationError("The uploaded file is not a valid PDF.") from exc

    try:
        if document.needs_pass:
            raise PDFValidationError("The PDF is password-protected and cannot be processed.")
        if document.page_count < 1:
            raise PDFValidationError("The PDF contains no pages.")
        if document.page_count > settings.max_pdf_pages:
            raise PDFValidationError(f"The PDF may contain at most {settings.max_pdf_pages} pages.")
    finally:
        document.close()
