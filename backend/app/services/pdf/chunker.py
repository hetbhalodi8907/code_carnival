from __future__ import annotations

import re
from collections.abc import Sequence


class PDFChunkingError(ValueError):
    """Raised when PDF chunking configuration or extraction data is invalid."""


_PARAGRAPH_PATTERN = re.compile(r"\n(?:[ \t]*\n)+")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def _split_long_block(block: str, max_size: int) -> list[str]:
    """Split one oversized paragraph at whitespace without changing its words."""
    words = _WHITESPACE_PATTERN.split(block.strip())
    pieces: list[str] = []
    current = ""

    for word in words:
        candidate = f"{current} {word}" if current else word
        if len(candidate) > max_size and current:
            pieces.append(current)
            current = word
        else:
            current = candidate

    if current:
        pieces.append(current)
    return pieces


def _build_page_chunks(page: dict[str, object], chunk_size: int, chunk_overlap: int) -> list[dict[str, object]]:
    page_number = int(page["page_number"])
    text = str(page["cleaned_text"] or "")
    blocks = [block.strip() for block in _PARAGRAPH_PATTERN.split(text) if block.strip()]
    pieces: list[str] = []

    for block in blocks:
        if len(block) <= chunk_size:
            pieces.append(block)
            continue
        pieces.extend(_split_long_block(block, chunk_size))

    chunks: list[dict[str, object]] = []
    current = ""
    for piece in pieces:
        candidate = f"{current} {piece}" if current else piece
        if current and len(candidate) > chunk_size:
            chunks.append(_make_chunk(current, page_number, len(chunks)))
            overlap = current[-chunk_overlap:] if chunk_overlap else ""
            current = f"{overlap} {piece}".strip()
        else:
            current = candidate

    if current:
        chunks.append(_make_chunk(current, page_number, len(chunks)))

    return chunks


def _make_chunk(content: str, page_number: int, chunk_index: int) -> dict[str, object]:
    return {
        "chunk_index": chunk_index,
        "content": content,
        "page_number": page_number,
        "source_locator": f"page:{page_number}",
        "metadata": {
            "source_type": "pdf",
            "page_number": page_number,
            "chunk_index": chunk_index,
        },
    }


def chunk_pdf_pages(
    extraction: dict[str, object],
    *,
    chunk_size: int = 4000,
    chunk_overlap: int = 200,
) -> list[dict[str, object]]:
    """Create deterministic, page-local chunks from cleaned PDF extraction data."""
    if chunk_size <= 0:
        raise PDFChunkingError("Chunk size must be greater than zero.")
    if chunk_overlap < 0:
        raise PDFChunkingError("Chunk overlap cannot be negative.")
    if chunk_overlap >= chunk_size:
        raise PDFChunkingError("Chunk overlap must be smaller than chunk size.")

    pages = extraction.get("pages")
    if not isinstance(pages, Sequence) or isinstance(pages, (str, bytes)):
        raise PDFChunkingError("PDF extraction contains no page list.")

    chunks: list[dict[str, object]] = []
    for page in pages:
        if not isinstance(page, dict):
            raise PDFChunkingError("PDF extraction contains an invalid page.")
        page_chunks = _build_page_chunks(page, chunk_size, chunk_overlap)
        for page_chunk in page_chunks:
            chunk_index = len(chunks)
            page_chunk["chunk_index"] = chunk_index
            page_chunk["metadata"]["chunk_index"] = chunk_index
            chunks.append(page_chunk)

    return chunks
