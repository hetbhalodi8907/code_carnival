import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fitz import open
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app import models
from app.db.session import create_database_engine, dispose_database_engine
from app.services.pdf.ingestion import PDFIngestionError, ingest_pdf
from auth_fixtures import clear_current_user_override, override_current_user, principal
from support import call_app


class PDFIngestionDatabaseTests(unittest.IsolatedAsyncioTestCase):
    engine: AsyncEngine
    session_factory: async_sessionmaker

    async def asyncSetUp(self) -> None:
        self.engine = create_database_engine()
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.storage_dir = Path(tempfile.mkdtemp(prefix="rag-pdf-ingestion-"))

        async with self.session_factory() as session:
            await session.execute(delete(models.DocumentChunk))
            await session.execute(delete(models.Document))
            await session.commit()

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        # The ingest API test uses the application's global engine; release it on this loop.
        await dispose_database_engine()
        for path in self.storage_dir.iterdir():
            path.unlink()
        self.storage_dir.rmdir()

    @staticmethod
    def create_pdf(path: Path) -> None:
        document = open()
        page_one = document.new_page(width=612, height=792)
        page_one.insert_text((72, 72), "First page\nFirst paragraph.\nSecond paragraph.")
        page_two = document.new_page(width=612, height=792)
        page_two.insert_text((72, 72), "Second page\nThird paragraph.")
        document.save(path)
        document.close()

    async def test_persistent_ingestion_creates_document_and_page_chunks(self) -> None:
        pdf_path = self.storage_dir / "test.pdf"
        self.create_pdf(pdf_path)
        content = pdf_path.read_bytes()

        with patch("app.services.pdf.ingestion.settings.document_storage_path", self.storage_dir):
            result = await ingest_pdf(
                filename="test.pdf",
                content_type="application/pdf",
                content=content,
                chunk_size=100,
                chunk_overlap=0,
                session_factory=self.session_factory,
            )

        async with self.session_factory() as session:
            document = await session.get(models.Document, result.document_id)
            chunks = await session.execute(
                select(models.DocumentChunk).where(
                    models.DocumentChunk.document_id == result.document_id
                )
            )
            stored_chunks = chunks.scalars().all()

        self.assertEqual(document.title, "test.pdf")
        self.assertEqual(document.source_type, "pdf")
        self.assertEqual(document.mime_type, "application/pdf")
        self.assertEqual(document.status, "processed")
        self.assertEqual(document.source_path, result.source_path)
        self.assertEqual(result.page_count, 2)
        self.assertEqual(result.chunk_count, len(stored_chunks))
        self.assertEqual([chunk.chunk_index for chunk in stored_chunks], list(range(len(stored_chunks))))
        self.assertEqual([chunk.page_number for chunk in stored_chunks], [1, 2])
        self.assertTrue(all(chunk.source_locator == f"page:{chunk.page_number}" for chunk in stored_chunks))
        self.assertTrue(all(chunk.chunk_metadata["source_type"] == "pdf" for chunk in stored_chunks))
        self.assertTrue((self.storage_dir / result.source_path).is_file())

    async def test_invalid_pdf_does_not_create_database_or_file_records(self) -> None:
        with patch("app.services.pdf.ingestion.settings.document_storage_path", self.storage_dir):
            with self.assertRaises(PDFIngestionError):
                await ingest_pdf(
                    filename="fake.pdf",
                    content_type="application/pdf",
                    content=b"not a pdf",
                    chunk_size=100,
                    chunk_overlap=0,
                    session_factory=self.session_factory,
                )

        async with self.session_factory() as session:
            documents = await session.execute(select(models.Document))
            chunks = await session.execute(select(models.DocumentChunk))

        self.assertEqual(documents.scalars().all(), [])
        self.assertEqual(chunks.scalars().all(), [])
        self.assertEqual(list(self.storage_dir.iterdir()), [])

    async def test_storage_failure_rolls_back_document_and_chunks(self) -> None:
        pdf_path = self.storage_dir / "test.pdf"
        self.create_pdf(pdf_path)
        content = pdf_path.read_bytes()

        original_write = Path.write_bytes

        def fail_write(self_path: Path, data: bytes) -> None:
            if self_path.name.endswith(".pdf"):
                raise OSError("simulated storage failure")
            return original_write(self_path, data)

        with patch("app.services.pdf.ingestion.settings.document_storage_path", self.storage_dir):
            with patch.object(Path, "write_bytes", fail_write):
                with self.assertRaises(PDFIngestionError):
                    await ingest_pdf(
                        filename="test.pdf",
                        content_type="application/pdf",
                        content=content,
                        chunk_size=100,
                        chunk_overlap=0,
                        session_factory=self.session_factory,
                    )

        async with self.session_factory() as session:
            documents = await session.execute(select(models.Document))
            chunks = await session.execute(select(models.DocumentChunk))

        self.assertEqual(documents.scalars().all(), [])
        self.assertEqual(chunks.scalars().all(), [])

    async def test_database_commit_failure_rolls_back_partial_ingestion(self) -> None:
        pdf_path = self.storage_dir / "test.pdf"
        self.create_pdf(pdf_path)
        content = pdf_path.read_bytes()

        async def fail_commit(session: AsyncSession) -> None:
            raise RuntimeError("simulated database failure")

        with patch("app.services.pdf.ingestion.settings.document_storage_path", self.storage_dir):
            with patch.object(AsyncSession, "commit", fail_commit):
                with self.assertRaises(PDFIngestionError):
                    await ingest_pdf(
                        filename="test.pdf",
                        content_type="application/pdf",
                        content=content,
                        chunk_size=100,
                        chunk_overlap=0,
                        session_factory=self.session_factory,
                    )

        async with self.session_factory() as session:
            documents = await session.execute(select(models.Document))
            chunks = await session.execute(select(models.DocumentChunk))

        self.assertEqual(documents.scalars().all(), [])
        self.assertEqual(chunks.scalars().all(), [])
        self.assertEqual(
            [path.name for path in self.storage_dir.iterdir() if path.name != "test.pdf"],
            [],
        )

    async def test_api_ingest_returns_structured_result(self) -> None:
        pdf_path = self.storage_dir / "test.pdf"
        self.create_pdf(pdf_path)
        content = pdf_path.read_bytes()
        boundary = "----pdf-ingest-api-test"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="test.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()

        async with self.session_factory() as session:
            uploader = models.User(email=f"uploader-{uuid4().hex}@example.invalid", full_name="Uploader")
            session.add(uploader)
            await session.commit()
        override_current_user(principal(uploader.id, "documents:write"))
        try:
            with patch("app.services.pdf.ingestion.settings.document_storage_path", self.storage_dir):
                status, headers, response = await call_app(
                    "POST",
                    "/api/v1/documents/ingest",
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                    body=body,
                )
        finally:
            clear_current_user_override()

        async with self.session_factory() as session:
            document = await session.scalar(select(models.Document))
            grants = (await session.execute(select(models.DocumentUserAccess))).scalars().all()
            self.assertEqual(document.owner_user_id, uploader.id)
            self.assertEqual([(g.document_id, g.user_id) for g in grants], [(document.id, uploader.id)])
            await session.execute(delete(models.Document))
            await session.execute(delete(models.User).where(models.User.id == uploader.id))
            await session.commit()

        self.assertEqual(status, 201)
        self.assertIn("x-request-id", headers)
        self.assertIn('"status":"processed"', response["body"])
        self.assertIn('"chunk_count":', response["body"])
        self.assertNotIn("/tmp", response["body"])
        self.assertNotIn("traceback", response["body"].lower())


if __name__ == "__main__":
    unittest.main()
