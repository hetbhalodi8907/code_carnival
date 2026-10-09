"""Image validation and OCR text extraction (Part 9).

Images are validated like any other upload (extension, declared type, size, real image
signature, decoded pixel cap) before OCR runs. OCR output is untrusted text: it is cleaned,
chunked, stored and retrieved exactly like PDF text, and is only ever shown to the model
as data inside a source boundary.

The default engine is RapidOCR (ONNX Runtime, models bundled in the pip package), so no
operating-system OCR installation is needed. If it cannot be imported, ``OCRUnavailableError``
says so; nothing is faked.
"""

from __future__ import annotations

import io
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.core.config import settings
from app.services.pdf.cleaner import clean_text


logger = logging.getLogger("app.ocr")

ALLOWED_EXTENSIONS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
_SIGNATURES = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}
OCR_ENGINE_NAME = "rapidocr-onnxruntime"


class ImageValidationError(ValueError):
    """The uploaded file is not a safe, supported image."""


class OCRUnavailableError(RuntimeError):
    """No OCR engine can be loaded in this environment."""


class OCRFailedError(RuntimeError):
    """The OCR engine failed on this image."""


class OCREmptyError(RuntimeError):
    """OCR ran but found no usable text."""


class OCREngine(Protocol):
    def recognize(self, image: bytes) -> list[tuple[str, float]]:
        """Return (text, confidence 0-1) per recognized line, in reading order."""


@dataclass(frozen=True)
class OCRResult:
    text: str
    line_count: int
    mean_confidence: float
    engine: str


def validate_image_upload(filename: str, content_type: str | None, content: bytes) -> str:
    """Validate an image upload and return its canonical MIME type."""
    if not filename.strip():
        raise ImageValidationError("An image filename is required.")
    expected = ALLOWED_EXTENSIONS.get(Path(filename).suffix.lower())
    if expected is None:
        raise ImageValidationError("Only PNG and JPEG images are supported.")
    if content_type is not None and content_type.lower() not in {expected, "image/jpg"}:
        raise ImageValidationError("The uploaded file is not the declared image type.")
    if not content:
        raise ImageValidationError("The uploaded image is empty.")
    if not content.startswith(_SIGNATURES[expected]):
        raise ImageValidationError("The uploaded file is not a valid image.")

    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise ImageValidationError("The uploaded file is not a valid image.") from exc
    if width * height > settings.max_image_pixels:
        raise ImageValidationError("The image dimensions are too large.")
    return expected


class RapidOCREngine:
    """RapidOCR (PP-OCR models on ONNX Runtime); the model loads once per process."""

    _lock = threading.Lock()
    _engine: Any = None

    def _load(self) -> Any:
        with self._lock:
            if RapidOCREngine._engine is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR
                except ImportError as exc:
                    raise OCRUnavailableError(
                        "OCR is unavailable: install it with `pip install rapidocr-onnxruntime`."
                    ) from exc
                RapidOCREngine._engine = RapidOCR()
            return RapidOCREngine._engine

    def recognize(self, image: bytes) -> list[tuple[str, float]]:
        engine = self._load()
        try:
            result, _ = engine(image)
        except Exception as exc:
            logger.warning("OCR engine failed error_type=%s", type(exc).__name__)
            raise OCRFailedError("The image could not be processed by OCR.") from None
        return [(str(text), float(confidence)) for _, text, confidence in (result or [])]


def ocr_available() -> bool:
    try:
        RapidOCREngine()._load()
    except OCRUnavailableError:
        return False
    return True


def extract_image_text(image: bytes, engine: OCREngine | None = None) -> OCRResult:
    """OCR a validated image: drop low-confidence lines and return cleaned text."""
    lines = (engine or RapidOCREngine()).recognize(image)
    kept = [(text.strip(), confidence) for text, confidence in lines
            if text.strip() and confidence >= settings.ocr_min_confidence]
    text = clean_text("\n".join(text for text, _ in kept))
    if not text:
        raise OCREmptyError("No readable text was found in the image.")
    return OCRResult(
        text=text,
        line_count=len(kept),
        mean_confidence=round(sum(confidence for _, confidence in kept) / len(kept), 4),
        engine=OCR_ENGINE_NAME,
    )


def ocr_to_extraction(result: OCRResult) -> dict[str, object]:
    """Shape OCR output like a one-page PDF extraction, so the existing chunker applies."""
    return {
        "page_count": 1,
        "pages": [{"page_number": 1, "text": result.text, "cleaned_text": result.text}],
        "text": result.text,
        "has_extractable_text": True,
    }
