"""Render demo documents to deterministic, text-extractable PDFs with PyMuPDF."""

from __future__ import annotations

from fitz import get_text_length, open as open_pdf

from demo_dataset.content import Page
from demo_dataset.spec import ORGANIZATION, DocumentSpec


PAGE_WIDTH = 612
PAGE_HEIGHT = 792
MARGIN = 72
TEXT_WIDTH = PAGE_WIDTH - 2 * MARGIN
BODY_BOTTOM = PAGE_HEIGHT - MARGIN

REGULAR_FONT = "helv"
BOLD_FONT = "hebo"
HEADER_SIZE = 8
TITLE_SIZE = 13
PAGE_HEADING_SIZE = 15
SECTION_HEADING_SIZE = 11.5
BODY_SIZE = 10
LINE_SPACING = 1.4

# Fixed metadata keeps output byte-identical across runs.
FIXED_PDF_DATE = "D:20250401000000Z"


class PDFLayoutError(ValueError):
    """Raised when page content does not fit on one PDF page."""


def wrap_text(text: str, *, fontname: str, fontsize: float, width: float = TEXT_WIDTH) -> list[str]:
    """Greedy word wrap using the font's real glyph widths."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if current and get_text_length(candidate, fontname=fontname, fontsize=fontsize) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def classification_label(document: DocumentSpec) -> str:
    return document.classification.replace("_", " ")


class _PageWriter:
    def __init__(self, page: object, *, filename: str) -> None:
        self._page = page
        self._filename = filename
        self._y = MARGIN

    def write(self, text: str, *, fontname: str, fontsize: float, space_before: float = 0) -> None:
        self._y += space_before
        for line in wrap_text(text, fontname=fontname, fontsize=fontsize):
            self._y += fontsize * LINE_SPACING
            if self._y > BODY_BOTTOM:
                raise PDFLayoutError(f"Content overflows a page in {self._filename}.")
            self._page.insert_text((MARGIN, self._y), line, fontname=fontname, fontsize=fontsize)


def _render_page(pdf: object, document: DocumentSpec, page: Page, page_number: int) -> None:
    page_count = len(document.pages)
    pdf_page = pdf.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    writer = _PageWriter(pdf_page, filename=document.filename)

    writer.write(
        f"{ORGANIZATION} | {classification_label(document)}",
        fontname=REGULAR_FONT,
        fontsize=HEADER_SIZE,
    )
    if page_number == 1:
        writer.write(document.title, fontname=BOLD_FONT, fontsize=TITLE_SIZE, space_before=6)
    writer.write(page.heading, fontname=BOLD_FONT, fontsize=PAGE_HEADING_SIZE, space_before=8)
    for section in page.sections:
        writer.write(section.heading, fontname=BOLD_FONT, fontsize=SECTION_HEADING_SIZE, space_before=8)
        for paragraph in section.paragraphs:
            writer.write(paragraph, fontname=REGULAR_FONT, fontsize=BODY_SIZE, space_before=3)

    pdf_page.insert_text(
        (MARGIN, PAGE_HEIGHT - MARGIN / 2),
        f"Synthetic demo document. {ORGANIZATION} is fictional. Page {page_number} of {page_count}",
        fontname=REGULAR_FONT,
        fontsize=HEADER_SIZE,
    )


def build_pdf(document: DocumentSpec) -> bytes:
    """Return the deterministic PDF bytes for one demo document."""
    pdf = open_pdf()
    try:
        pdf.set_metadata(
            {
                "title": document.title,
                "author": f"{ORGANIZATION} (synthetic demo data)",
                "subject": document.description,
                "keywords": document.classification,
                "creator": "nexora-demo dataset generator",
                "producer": "PyMuPDF",
                "creationDate": FIXED_PDF_DATE,
                "modDate": FIXED_PDF_DATE,
            }
        )
        for page_number, page in enumerate(document.pages, start=1):
            _render_page(pdf, document, page, page_number)
        return pdf.tobytes(garbage=4, deflate=True, no_new_id=True)
    finally:
        pdf.close()
