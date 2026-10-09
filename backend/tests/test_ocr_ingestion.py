"""Part 9: image validation, OCR ingestion, grants and the upload endpoint."""

import io
import json
import unittest
from unittest.mock import patch

from sqlalchemy import func, select

from app import models
from app.core.config import settings
from app.services.ocr.ingestion import ingest_image
from app.services.ocr.ocr import (
    ImageValidationError,
    OCREmptyError,
    OCRFailedError,
    OCRUnavailableError,
    RapidOCREngine,
    extract_image_text,
    ocr_available,
    validate_image_upload,
)
from app.services.pdf.ingestion import PDFIngestionError
from app.services.vector_search import VectorSearchService
from demo_dataset.ocr_image import OCR_DEMO_FILENAME, OCR_DEMO_LINES, build_demo_notice_png
from demo_fixtures import DemoDatasetTestCase, lexical_service
from support import call_app


PNG = build_demo_notice_png()
SUPER_ADMIN = "ishaan.malhotra@nexora.example"
FINANCE_MANAGER = "vikram.nair@nexora.example"
KABIR = "kabir.sethi@nexora.example"


class FakeOCR:
    def __init__(self, lines=None, error: Exception | None = None) -> None:
        self.lines = lines if lines is not None else [("Quarterly facilities schedule", 0.98), ("Lift maintenance on Friday", 0.95)]
        self.error = error
        self.calls = 0

    def recognize(self, image: bytes):
        self.calls += 1
        if self.error:
            raise self.error
        return self.lines


def png_of(width: int, height: int) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, "PNG")
    return buffer.getvalue()


def multipart(filename: str, content: bytes, content_type: str) -> tuple[bytes, dict[str, str]]:
    boundary = "----nexora-test"
    head = f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'
    return head.encode() + content + f"\r\n--{boundary}--\r\n".encode(), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


class ImageValidationTests(unittest.TestCase):
    def test_valid_png_and_jpeg_are_accepted(self) -> None:
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (20, 20), "white").save(buffer, "JPEG")
        self.assertEqual(validate_image_upload("a.png", "image/png", PNG), "image/png")
        self.assertEqual(validate_image_upload("a.JPG", "image/jpeg", buffer.getvalue()), "image/jpeg")
        self.assertEqual(validate_image_upload("a.jpeg", None, buffer.getvalue()), "image/jpeg")

    def test_unsafe_or_mismatched_uploads_are_rejected(self) -> None:
        cases = {
            "no name": ("", "image/png", PNG),
            "pdf extension": ("a.pdf", "application/pdf", PNG),
            "svg": ("a.svg", "image/svg+xml", b"<svg onload=alert(1)/>"),
            "wrong declared type": ("a.png", "application/pdf", PNG),
            "empty": ("a.png", "image/png", b""),
            "text renamed .png": ("a.png", "image/png", b"not an image at all"),
            "jpeg named .png": ("a.png", "image/png", b"\xff\xd8\xff" + b"0" * 50),
            "truncated png": ("a.png", "image/png", PNG[:200]),
        }
        for label, (name, content_type, content) in cases.items():
            with self.subTest(label), self.assertRaises(ImageValidationError):
                validate_image_upload(name, content_type, content)

    def test_oversized_dimensions_are_rejected_before_decoding_pixels(self) -> None:
        with patch.object(settings, "max_image_pixels", 100 * 100):
            with self.assertRaisesRegex(ImageValidationError, "too large"):
                validate_image_upload("a.png", "image/png", png_of(200, 200))
            validate_image_upload("a.png", "image/png", png_of(100, 100))


class OCRExtractionTests(unittest.TestCase):
    def test_low_confidence_and_blank_lines_are_dropped(self) -> None:
        engine = FakeOCR([("Clear line", 0.97), ("   ", 0.99), ("garbled #@!", 0.2), ("Another clear line", 0.9)])
        result = extract_image_text(PNG, engine)
        self.assertEqual(result.text, "Clear line\nAnother clear line")
        self.assertEqual((result.line_count, result.mean_confidence), (2, 0.935))

    def test_no_text_is_a_clear_error_not_an_empty_document(self) -> None:
        for lines in ([], [("faint", 0.1)], [("  ", 0.99)]):
            with self.subTest(lines=lines), self.assertRaises(OCREmptyError):
                extract_image_text(PNG, FakeOCR(lines))

    def test_unavailable_engine_is_reported_honestly(self) -> None:
        with patch.dict("sys.modules", {"rapidocr_onnxruntime": None}), patch.object(RapidOCREngine, "_engine", None):
            with self.assertRaisesRegex(OCRUnavailableError, "pip install rapidocr-onnxruntime"):
                RapidOCREngine().recognize(PNG)

    @unittest.skipUnless(ocr_available(), "OCR engine is not installed")
    def test_real_ocr_reads_the_demo_notice(self) -> None:
        result = extract_image_text(PNG)
        for line in OCR_DEMO_LINES[1:]:
            self.assertIn(line, result.text)
        self.assertGreater(result.mean_confidence, 0.9)


class OCRIngestionTests(DemoDatasetTestCase):
    EMBED = False

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.embeddings = lexical_service()
        self.search = VectorSearchService(
            self.session_factory, embedding_dimension=self.embeddings.dimension, embedding_model=self.embeddings.model
        )

    async def ingest(self, email: str | None, engine=None, **kwargs):
        return await ingest_image(
            filename="schedule.png", content_type="image/png", content=PNG, session_factory=self.session_factory,
            owner_user_id=self.user_id(email) if email else None, embedding_service=self.embeddings,
            engine=engine or FakeOCR(), **kwargs,
        )

    async def found_by(self, email: str, query: str = "lift maintenance schedule") -> list:
        return await self.search.search_text(query, top_k=20, embedding_service=self.embeddings, user_id=self.user_id(email))

    async def test_ingestion_creates_an_embedded_image_document_with_ocr_metadata(self) -> None:
        result = await self.ingest(KABIR)
        self.assertEqual((result.chunk_count, result.embedding_status, result.ocr_line_count), (1, "completed", 2))
        async with self.session_factory() as session:
            document = await session.get(models.Document, result.document_id)
            chunk = (await session.scalars(select(models.DocumentChunk).where(models.DocumentChunk.document_id == result.document_id))).one()
        self.assertEqual((document.source_type, document.mime_type, document.owner_user_id), ("image", "image/png", self.user_id(KABIR)))
        self.assertTrue(document.source_path.endswith(".png"))
        self.assertEqual((chunk.page_number, chunk.source_locator, chunk.embedding_model), (None, "image:ocr", self.embeddings.model))
        self.assertEqual(chunk.chunk_metadata["source_type"], "image")
        self.assertEqual(chunk.chunk_metadata["ocr_engine"], "rapidocr-onnxruntime")
        self.assertEqual(chunk.chunk_metadata["ocr_line_count"], 2)
        self.assertEqual(len(chunk.embedding), self.embeddings.dimension)
        self.assertIn("Lift maintenance on Friday", chunk.content)

    async def test_only_the_uploader_can_retrieve_it_until_a_grant_exists(self) -> None:
        await self.ingest(KABIR)
        mine = await self.found_by(KABIR)
        self.assertEqual({r.source_type for r in mine if "Lift" in r.content}, {"image"})
        for email in (FINANCE_MANAGER, SUPER_ADMIN, "meera.iyer@nexora.example"):
            with self.subTest(user=email):
                self.assertFalse([r for r in await self.found_by(email) if "Lift maintenance" in r.content])

        async with self.session_factory() as session:  # an explicit grant is the only way to share it
            document_id = (await session.scalars(select(models.Document.id).where(models.Document.title == "schedule.png"))).one()
            role_id = await session.scalar(select(models.Role.id).where(models.Role.name == "FINANCE_MANAGER"))
            session.add(models.DocumentRoleAccess(document_id=document_id, role_id=role_id))
            await session.commit()
        self.assertTrue([r for r in await self.found_by(FINANCE_MANAGER) if "Lift maintenance" in r.content])
        self.assertFalse([r for r in await self.found_by(SUPER_ADMIN) if "Lift maintenance" in r.content])  # no admin bypass

    async def test_empty_failed_and_invalid_images_persist_nothing(self) -> None:
        async def documents() -> int:
            async with self.session_factory() as session:
                return await session.scalar(select(func.count()).select_from(models.Document))

        before = await documents()
        for engine, error in ((FakeOCR([]), OCREmptyError), (FakeOCR(error=OCRFailedError("boom")), OCRFailedError)):
            with self.assertRaises(error):
                await self.ingest(KABIR, engine=engine)
        with self.assertRaises(ImageValidationError):
            await ingest_image(filename="x.png", content_type="image/png", content=b"nope", session_factory=self.session_factory,
                               owner_user_id=None, embedding_service=self.embeddings, engine=FakeOCR())
        self.assertEqual(await documents(), before)

    async def test_embedding_failure_keeps_the_document_but_reports_it(self) -> None:
        from app.services.embeddings.provider import EmbeddingConfigurationError

        with patch("app.services.embeddings.service.create_embedding_service", side_effect=EmbeddingConfigurationError("x")):
            result = await ingest_image(filename="s.png", content_type="image/png", content=PNG, session_factory=self.session_factory,
                                        owner_user_id=self.user_id(KABIR), engine=FakeOCR())
        self.assertEqual(result.embedding_status, "not_configured")
        self.assertFalse(await self.found_by(KABIR))  # stored, but not searchable until embedded

    async def test_a_stored_file_is_never_overwritten(self) -> None:
        first = await self.ingest(KABIR)
        with self.assertRaises(PDFIngestionError):
            await self.ingest(KABIR, document_id=first.document_id)


class ImageUploadEndpointTests(DemoDatasetTestCase):
    EMBED = False
    PATH = "/api/v1/documents/ingest-image"

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        patcher = patch("app.services.embeddings.service.create_embedding_service", side_effect=lexical_service)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def upload(self, email: str | None, filename="notice.png", content=PNG, content_type="image/png"):
        body, headers = multipart(filename, content, content_type)
        if email:
            headers.update(self.token_headers(self.user_id(email)))
        status, _, response = await call_app("POST", self.PATH, headers=headers, body=body)
        return status, json.loads(response["body"])

    async def test_authentication_and_write_permission_are_required(self) -> None:
        self.assertEqual((await self.upload(None))[0], 401)
        status, body = await self.upload(FINANCE_MANAGER)  # documents:read only
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["message"], "You do not have permission to perform this action.")
        async with self.session_factory() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(models.Document).where(models.Document.source_type == "image")), 0)

    @unittest.skipUnless(ocr_available(), "OCR engine is not installed")
    async def test_authorized_upload_runs_real_ocr_and_grants_only_the_uploader(self) -> None:
        status, body = await self.upload(SUPER_ADMIN, filename=OCR_DEMO_FILENAME)
        self.assertEqual(status, 201, body)
        self.assertEqual((body["source_type"], body["embedding_status"], body["status"]), ("image", "completed", "processed"))
        self.assertGreaterEqual(body["ocr_mean_confidence"], 0.9)
        async with self.session_factory() as session:
            grants = (await session.scalars(select(models.DocumentUserAccess.user_id).where(models.DocumentUserAccess.document_id == body["document_id"]))).all()
            roles = await session.scalar(select(func.count()).select_from(models.DocumentRoleAccess).where(models.DocumentRoleAccess.document_id == body["document_id"]))
        self.assertEqual((list(grants), roles), ([self.user_id(SUPER_ADMIN)], 0))

    async def test_invalid_oversized_and_unreadable_images_get_safe_errors(self) -> None:
        self.assertEqual((await self.upload(SUPER_ADMIN, filename="x.exe", content_type="application/octet-stream"))[0], 400)
        self.assertEqual((await self.upload(SUPER_ADMIN, content=b"not an image"))[0], 400)
        with patch.object(settings, "max_image_size_mb", 0):
            status, body = await self.upload(SUPER_ADMIN)
        self.assertEqual(status, 413)
        blank = png_of(300, 120)  # a valid image with no text
        if ocr_available():
            status, body = await self.upload(SUPER_ADMIN, content=blank)
            self.assertEqual((status, body["error"]["message"]), (422, "No readable text was found in the image."))

    async def test_missing_ocr_engine_is_a_503_not_a_fake_success(self) -> None:
        with patch.dict("sys.modules", {"rapidocr_onnxruntime": None}), patch.object(RapidOCREngine, "_engine", None):
            status, body = await self.upload(SUPER_ADMIN)
        self.assertEqual((status, body["error"]["message"]), (503, "OCR is not available on the server."))


if __name__ == "__main__":
    unittest.main()
