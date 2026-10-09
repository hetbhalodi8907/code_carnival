from __future__ import annotations

from pathlib import Path
from typing import Protocol

from fitz import FileDataError, open

from app.core.config import settings


class PDFDocument(Protocol):
    """Minimal protocol implemented by PyMuPDF documents."""

    def page_count(self) -> int: ...


class PDFValidationError(ValueError):
    """Raised when an uploaded file is not safe or valid PDF input."""


def validate_pdf_upload(filename: str, content_type: str | None, content: bytes) -> None:
    """Validate a filename, MIME hint, size, and actual PDF structure."""
    if not filename.strip():
        raise PDFValidationError("A PDF filename is required.")

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
        if document.page_count < 1:
            raise PDFValidationError("The PDF contains no pages.")
    finally:
        document.close()
