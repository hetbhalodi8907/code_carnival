"""PDF upload -> index -> secure retrieval -> assistant answer, end to end.

Real authentication, upload endpoint, local sentence-transformers model (384 dimensions),
pgvector storage and SQL-level authorization on rag_system_test. Only the LLM is fake, so the
test can record exactly what the model would be sent.
"""

import json
import re
import unittest
from unittest.mock import patch

from fitz import open as open_pdf
from sqlalchemy import func, select, text

from app import models
from app.core.config import settings
from app.models.document_chunk import EMBEDDING_VECTOR_DIMENSION
from app.services.embeddings.provider import EmbeddingProviderError
from app.services.embeddings.service import create_embedding_service
from app.services.llm.provider import LLMProvider, LLMResponse
from app.services.rag.generation import AnswerGenerator
from app.services.vector_search import VectorSearchService
from demo_fixtures import DemoDatasetTestCase
from support import call_app


UPLOAD = "/api/v1/documents/ingest"
QUERY = "/api/v1/assistant/query"
UPLOADER = "ishaan.malhotra@nexora.example"  # SUPER_ADMIN: the only demo role with documents:write
OTHERS = (
    "vikram.nair@nexora.example",
    "meera.iyer@nexora.example",
    "ananya.rao@nexora.example",
    "devika.krishnan@nexora.example",
    "kabir.sethi@nexora.example",
)
QUESTION = "What is the Aurora launch budget and the launch codename?"
FACT = "The Aurora launch budget is INR 7.35 crore and the launch codename is zebra-lantern."


def synthetic_pdf() -> bytes:
    document = open_pdf()
    document.new_page().insert_text((72, 72), "Project Aurora charter\nAurora is the new customer analytics platform.\nThe steering group meets monthly.")
    document.new_page().insert_text((72, 72), "Aurora launch plan\n" + FACT)
    content = document.tobytes()
    document.close()
    return content


def multipart(filename: str, content: bytes, content_type: str, extra: dict[str, str] | None = None) -> tuple[bytes, dict[str, str]]:
    boundary = "----nexora-pdf-test"
    parts = b""
    for name, value in (extra or {}).items():
        parts += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    parts += f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode()
    return parts + content + f"\r\n--{boundary}--\r\n".encode(), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


class RecordingProvider(LLMProvider):
    """Answers by citing whichever source contains the Aurora budget, and records each prompt."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    @property
    def model(self) -> str:
        return "fake-llm"

    async def generate(self, messages, *, temperature=None, max_tokens=None):  # noqa: ANN001
        prompt = "\n".join(message.content for message in messages)
        self.prompts.append(prompt)
        match = re.search(r"SOURCE (\d+) \[[0-9a-f]+\] ---(?:(?!--- END).)*?INR 7\.35 crore", prompt, re.DOTALL)
        cite = f" [S{match.group(1)}]" if match else ""
        return LLMResponse(f"The Aurora launch budget is INR 7.35 crore{cite}.", "fake-llm", "stop", 10, 5)


class PDFUploadPipelineTests(DemoDatasetTestCase):
    EMBED = False

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from sentence_transformers import SentenceTransformer

            SentenceTransformer(settings.embedding_model, device="cpu", local_files_only=True)
        except Exception:  # noqa: BLE001 - any cache miss means the model is not downloaded
            raise unittest.SkipTest("the local embedding model is not in the Hugging Face cache") from None
        super().setUpClass()

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.provider = RecordingProvider()
        patcher = patch("app.api.v1.assistant.create_answer_generator", side_effect=lambda: AnswerGenerator(self.provider))
        patcher.start()
        self.addCleanup(patcher.stop)

    async def upload(self, email: str | None, filename="aurora.pdf", content=None, content_type="application/pdf", extra=None):
        body, headers = multipart(filename, synthetic_pdf() if content is None else content, content_type, extra)
        if email:
            headers.update(self.token_headers(self.user_id(email)))
        status, _, response = await call_app("POST", UPLOAD, headers=headers, body=body)
        return status, json.loads(response["body"])

    async def ask(self, email: str, question: str = QUESTION) -> dict:
        status, _, body = await self.request_json("POST", QUERY, {"query": question, "top_k": 10}, self.token_headers(self.user_id(email)))
        self.assertEqual(status, 200, body)
        return body

    async def count_documents(self) -> int:
        async with self.session_factory() as session:
            return await session.scalar(select(func.count()).select_from(models.Document).where(models.Document.title == "aurora.pdf"))

    # ---- the full path -------------------------------------------------------------------------

    async def test_upload_is_indexed_and_immediately_answerable_by_the_uploader_only(self) -> None:
        status, body = await self.upload(UPLOADER)
        self.assertEqual(status, 201, body)
        self.assertEqual(
            (body["status"], body["source_type"], body["page_count"], body["embedding_status"], body["embedding_model"]),
            ("processed", "pdf", 2, "completed", "sentence-transformers/all-MiniLM-L6-v2"),
        )
        document_id = body["document_id"]
        self.assertNotIn("/", body["source_path"])

        # Persisted: document, page-wise chunks with metadata, 384-d embeddings with the model name.
        async with self.session_factory() as session:
            document = await session.get(models.Document, document_id)
            chunks = (await session.scalars(select(models.DocumentChunk).where(models.DocumentChunk.document_id == document.id).order_by(models.DocumentChunk.chunk_index))).all()
            dims = (await session.execute(text("select min(vector_dims(embedding)), max(vector_dims(embedding)) from document_chunks where document_id = :d"), {"d": document.id})).one()
            grants = (await session.scalars(select(models.DocumentUserAccess.user_id).where(models.DocumentUserAccess.document_id == document.id))).all()
            role_grants = await session.scalar(select(func.count()).select_from(models.DocumentRoleAccess).where(models.DocumentRoleAccess.document_id == document.id))
        self.assertEqual((document.title, document.owner_user_id, document.source_type), ("aurora.pdf", self.user_id(UPLOADER), "pdf"))
        self.assertEqual([c.page_number for c in chunks], [1, 2])
        self.assertEqual([c.source_locator for c in chunks], ["page:1", "page:2"])
        self.assertEqual({c.embedding_model for c in chunks}, {settings.embedding_model})
        self.assertEqual(tuple(dims), (EMBEDDING_VECTOR_DIMENSION, EMBEDDING_VECTOR_DIMENSION))
        self.assertEqual(EMBEDDING_VECTOR_DIMENSION, 384)
        # Default deny: the only grant is the uploader's own.
        self.assertEqual((list(grants), role_grants), ([self.user_id(UPLOADER)], 0))

        # Immediately retrievable by the uploader, with real source metadata and a valid citation.
        answer = await self.ask(UPLOADER)
        mine = [s for s in answer["sources"] if s["document_id"] == document_id]
        self.assertTrue(mine, answer["sources"])
        budget_page = next(s for s in mine if s["page_number"] == 2)
        self.assertEqual((budget_page["document_title"], budget_page["source_locator"], budget_page["source_type"]), ("aurora.pdf", "page:2", "pdf"))
        self.assertEqual((answer["status"], answer["citation_check"], budget_page["cited"]), ("answered", "passed", True))
        self.assertIn("INR 7.35 crore", self.provider.prompts[-1])

    async def test_other_accounts_cannot_retrieve_it_and_the_model_never_sees_it(self) -> None:
        status, body = await self.upload(UPLOADER)
        self.assertEqual(status, 201, body)
        document_id = body["document_id"]

        embeddings = create_embedding_service()
        search = VectorSearchService(self.session_factory, embedding_dimension=embeddings.dimension, embedding_model=embeddings.model)
        for email in (*OTHERS, "ishaan.malhotra@nexora.example"):
            self.provider.prompts.clear()
            results = await search.search_text(QUESTION, top_k=20, embedding_service=embeddings, user_id=self.user_id(email))
            expected = email == UPLOADER
            self.assertEqual(any(str(r.document_id) == document_id for r in results), expected, email)
        for email in OTHERS:
            with self.subTest(user=email):
                self.provider.prompts.clear()
                answer = await self.ask(email)
                self.assertNotIn(document_id, json.dumps(answer))
                self.assertNotIn("aurora.pdf", json.dumps(answer))
                for prompt in self.provider.prompts:
                    for secret in ("zebra-lantern", "7.35", "Project Aurora"):
                        self.assertNotIn(secret, prompt)

    async def test_identity_comes_from_the_token_not_the_upload(self) -> None:
        status, body = await self.upload(UPLOADER, extra={"owner_user_id": str(self.user_id(OTHERS[0])), "role": "SUPER_ADMIN", "user_id": str(self.user_id(OTHERS[0]))})
        self.assertEqual(status, 201, body)
        async with self.session_factory() as session:
            document = await session.get(models.Document, body["document_id"])
            grants = (await session.scalars(select(models.DocumentUserAccess.user_id).where(models.DocumentUserAccess.document_id == document.id))).all()
        self.assertEqual((document.owner_user_id, list(grants)), (self.user_id(UPLOADER), [self.user_id(UPLOADER)]))

    # ---- validation and failure ------------------------------------------------------------------------

    async def test_unauthenticated_unpermitted_and_invalid_uploads_persist_nothing(self) -> None:
        self.assertEqual((await self.upload(None))[0], 401)
        self.assertEqual((await self.upload("vikram.nair@nexora.example"))[0], 403)  # documents:read only
        cases = {
            "wrong extension": dict(filename="aurora.txt", content_type="text/plain"),
            "wrong declared type": dict(content_type="image/png"),
            "not a pdf": dict(content=b"this is plain text, not a pdf"),
            "empty": dict(content=b""),
            "truncated pdf": dict(content=synthetic_pdf()[:120]),
        }
        for label, kwargs in cases.items():
            with self.subTest(label):
                status, body = await self.upload(UPLOADER, **kwargs)
                self.assertIn(status, (400, 422), body)
        with patch.object(settings, "max_pdf_size_mb", 0):
            self.assertEqual((await self.upload(UPLOADER))[0], 413)
        self.assertEqual(await self.count_documents(), 0)

    async def test_embedding_failure_keeps_the_upload_but_reports_it_and_stays_unsearchable(self) -> None:
        with patch("app.services.embeddings.service.create_embedding_service", side_effect=EmbeddingProviderError("boom")):
            status, body = await self.upload(UPLOADER)
        self.assertEqual((status, body["embedding_status"], body["embedding_model"]), (201, "failed", None))
        answer = await self.ask(UPLOADER)
        self.assertNotIn(body["document_id"], json.dumps(answer))  # un-embedded chunks are never returned
        # The existing endpoint can embed it later.
        embedded = await self.request_json("POST", f"/api/v1/embeddings/documents/{body['document_id']}", {}, self.token_headers(self.user_id(UPLOADER)))
        self.assertEqual(embedded[0], 200)
        self.assertIn(body["document_id"], json.dumps(await self.ask(UPLOADER)))


if __name__ == "__main__":
    unittest.main()
