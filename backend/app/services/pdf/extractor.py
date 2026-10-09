from __future__ import annotations

from fitz import FileDataError, open

from app.services.pdf.cleaner import clean_text


class PDFExtractionError(RuntimeError):
    """Raised when a valid PDF cannot be processed safely."""


def extract_pdf_pages(content: bytes) -> dict[str, object]:
    """Extract and clean text separately for every PDF page."""
    try:
        document = open(stream=content, filetype="pdf")
    except (FileDataError, OSError, ValueError) as exc:
        raise PDFExtractionError("The PDF could not be opened for extraction.") from exc

    try:
        pages = []
        for page_number in range(1, document.page_count + 1):
            page = document[page_number - 1]
            extracted_text = page.get_text("text").strip()
            pages.append(
                {
                    "page_number": page_number,
                    "text": extracted_text,
                    "cleaned_text": clean_text(extracted_text),
                }
            )

        total_text = "\n\n".join(page["cleaned_text"] for page in pages if page["cleaned_text"])
        return {
            "page_count": document.page_count,
            "pages": pages,
            "text": total_text,
            "has_extractable_text": bool(total_text),
        }
    except (FileDataError, OSError, ValueError) as exc:
        raise PDFExtractionError("The PDF text could not be extracted.") from exc
    finally:
        document.close()
