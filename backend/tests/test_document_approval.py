"""CEO approval workflow for PDF and image uploads, end to end against rag_system_test.

Real authentication and authorization, real quarantine storage, and on approval the REAL existing ingestion
pipeline (PDF extraction or OCR, chunking, persistence, embeddings, grants). Embeddings use the offline lexical
stand-in and the language model is a recording stand-in: no provider quota is used.
"""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
from fitz import PDF_ENCRYPT_AES_256, open as open_pdf
from sqlalchemy import delete, func, select, text, update

from app import models
from app.core.config import settings
from app.main import app
from app.services.llm.provider import LLMResponse
from app.services.ocr.ocr import OCRFailedError
from app.services.pdf.ingestion import ingest_pdf
from app.services.rag.context import ContextBuilder
from app.services.rag.generation import AnswerGenerator
from app.services.submissions import storage
from app.services.vector_search import VectorSearchService
from demo_dataset.ocr_image import build_demo_notice_png
from demo_dataset.spec import PERMISSIONS, ROLES
from demo_fixtures import DemoDatasetTestCase, lexical_service
from test_document_chat import RecordingProvider, ScopedBuilder


SUBMIT = "/api/v1/document-submissions"
ROLE_USERS = {
    "SUPER_ADMIN": "ishaan.malhotra@nexora.example",
    "FINANCE_MANAGER": "vikram.nair@nexora.example",
    "HR_MANAGER": "meera.iyer@nexora.example",
    "ENGINEERING_MANAGER": "ananya.rao@nexora.example",
    "SECURITY_MANAGER": "devika.krishnan@nexora.example",
    "EMPLOYEE": "kabir.sethi@nexora.example",
}
CEO = ROLE_USERS["SUPER_ADMIN"]
NON_CEO = {role: email for role, email in ROLE_USERS.items() if role != "SUPER_ADMIN"}
EMPLOYEE = ROLE_USERS["EMPLOYEE"]
FINANCE = ROLE_USERS["FINANCE_MANAGER"]
NOT_FOUND = "The submission was not found."
FACT = "The Zephyr migration budget is INR 3.6 crore and the codename is quartz-heron."


def pdf_bytes(*pages: str, **options: object) -> bytes:
    document = open_pdf()
    for page_text in pages:
        page = document.new_page()
        if page_text:
            page.insert_text((72, 72), page_text)
    content = document.tobytes(**options)
    document.close()
    return content


PNG = build_demo_notice_png()


class ApprovalTestCase(DemoDatasetTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.quarantine = tempfile.TemporaryDirectory()
        self.addCleanup(self.quarantine.cleanup)
        self.provider = RecordingProvider()
        self.builders: list[ScopedBuilder] = []

        def make_builder(session_factory):  # noqa: ANN001
            embeddings = lexical_service()
            search = VectorSearchService(session_factory, embedding_dimension=embeddings.dimension, embedding_model=embeddings.model)
            builder = ScopedBuilder(search, embeddings)
            self.builders.append(builder)
            return builder

        for active in (
            patch.object(settings, "quarantine_storage_path", self.quarantine.name),
            patch("app.services.embeddings.service.create_embedding_service", side_effect=lexical_service),
            patch("app.api.v1.embeddings.create_embedding_service", side_effect=lexical_service),
            patch("app.services.rag.context.create_embedding_service", side_effect=lexical_service),
            patch("app.api.v1.assistant.create_document_context_builder", side_effect=make_builder),
            patch("app.api.v1.assistant.create_answer_generator", side_effect=lambda: AnswerGenerator(self.provider)),
        ):
            active.start()
            self.addCleanup(active.stop)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)

    async def asyncTearDown(self) -> None:
        async with self.session_factory() as session:
            await session.execute(delete(models.DocumentSubmission))  # only rows these tests created
            await session.commit()
        await super().asyncTearDown()

    # ---- helpers -----------------------------------------------------------------------------------------

    def auth(self, email: str) -> dict[str, str]:
        return self.token_headers(self.user_id(email))

    async def submit(self, email: str | None, filename: str = "plan.pdf", content: bytes | None = None, content_type: str = "application/pdf"):
        headers = self.auth(email) if email else {}
        data = pdf_bytes("Zephyr migration plan", FACT) if content is None else content
        return await self.client.post(SUBMIT, files={"file": (filename, data, content_type)}, headers=headers)

    async def counts(self) -> dict[str, int]:
        async with self.session_factory() as session:
            async def n(query):  # noqa: ANN001, ANN202
                return await session.scalar(query)

            return {
                "documents": await n(select(func.count()).select_from(models.Document)),
                "chunks": await n(select(func.count()).select_from(models.DocumentChunk)),
                "embedded": await n(select(func.count()).select_from(models.DocumentChunk).where(models.DocumentChunk.embedding.is_not(None))),
                "user_grants": await n(select(func.count()).select_from(models.DocumentUserAccess)),
                "role_grants": await n(select(func.count()).select_from(models.DocumentRoleAccess)),
            }

    def quarantined(self) -> list[str]:
        return sorted(path.name for path in Path(self.quarantine.name).iterdir())

    def active_files(self) -> set[str]:
        return {path.name for path in Path(settings.document_storage_path).iterdir()} if Path(settings.document_storage_path).exists() else set()

    async def documents_titled(self, title: str) -> list[models.Document]:
        async with self.session_factory() as session:
            return list(await session.scalars(select(models.Document).where(models.Document.title == title)))

    async def row(self, submission_id: str) -> models.DocumentSubmission:
        async with self.session_factory() as session:
            return await session.get(models.DocumentSubmission, UUID(submission_id))

    async def approve(self, submission_id: str, email: str = CEO):
        return await self.client.post(f"{SUBMIT}/{submission_id}/approve", headers=self.auth(email))

    async def reject(self, submission_id: str, email: str = CEO, reason: str | None = "Not appropriate"):
        return await self.client.post(f"{SUBMIT}/{submission_id}/reject", json={"reason": reason} if reason else None, headers=self.auth(email))


class SubmissionTests(ApprovalTestCase):
    async def test_all_six_roles_can_submit_a_pdf_and_an_image_and_nothing_becomes_active(self) -> None:
        before = await self.counts()
        for role, email in ROLE_USERS.items():
            pdf = await self.submit(email, f"{role}-plan.pdf")
            image = await self.submit(email, f"{role}-notice.png", PNG, "image/png")
            self.assertEqual((pdf.status_code, image.status_code), (201, 201), (role, pdf.text, image.text))
            for body, kind in ((pdf.json(), "pdf"), (image.json(), "image")):
                self.assertEqual((body["status"], body["source_type"], body["document_id"]), ("pending_approval", kind, None))
                self.assertTrue(body["preview_available"])
                self.assertNotIn("quarantine", json.dumps(body).lower())
                self.assertNotIn(self.quarantine.name, json.dumps(body))  # no filesystem path
        self.assertEqual(len(self.quarantined()), 12)
        # Pending is not active: no documents, chunks, embeddings or grants of any kind exist for them.
        self.assertEqual(await self.counts(), before)
        for name in self.quarantined():  # server-generated names only, private permissions
            self.assertRegex(name, r"^[0-9a-f-]{36}\.(pdf|png)$")
            self.assertEqual((Path(self.quarantine.name) / name).stat().st_mode & 0o777, 0o600)

    async def test_anonymous_and_unpermitted_callers_cannot_submit(self) -> None:
        self.assertEqual((await self.submit(None)).status_code, 401)
        self.assertEqual((await self.client.post(SUBMIT, headers={"Authorization": "Bearer nope"})).status_code, 401)
        async with self.session_factory() as session:
            user = models.User(email=f"nosubmit-{uuid4().hex}@example.invalid", full_name="No Submit", is_active=True)
            session.add(user)
            await session.commit()
            user_id = user.id
        response = await self.client.post(SUBMIT, files={"file": ("a.pdf", pdf_bytes("x"), "application/pdf")}, headers=self.token_headers(user_id))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.quarantined(), [])

    async def test_invalid_oversized_and_unreadable_files_never_enter_the_queue(self) -> None:
        locked = pdf_bytes("Secret table", encryption=PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="owner")
        cases = {
            "wrong extension": ("plan.txt", b"hello", "text/plain"),
            "svg": ("logo.svg", b"<svg/>", "image/svg+xml"),
            "pdf declared as png": ("plan.pdf", pdf_bytes("x"), "image/png"),
            "not a pdf": ("plan.pdf", b"this is plain text", "application/pdf"),
            "empty pdf": ("plan.pdf", b"", "application/pdf"),
            "truncated pdf": ("plan.pdf", pdf_bytes("x")[:100], "application/pdf"),
            "password protected": ("plan.pdf", locked, "application/pdf"),
            "blank pdf (no text)": ("plan.pdf", pdf_bytes("", ""), "application/pdf"),
            "fake png": ("notice.png", b"not really an image", "image/png"),
            "png with jpeg extension": ("notice.jpg", PNG, "image/jpeg"),
            "jpeg declared as png": ("notice.png", b"\xff\xd8\xff\xe0" + b"0" * 50, "image/png"),
        }
        for label, (name, data, content_type) in cases.items():
            with self.subTest(label):
                response = await self.submit(EMPLOYEE, name, data, content_type)
                self.assertIn(response.status_code, (400, 422), response.text)
        with patch.object(settings, "max_pdf_size_mb", 0):
            self.assertEqual((await self.submit(EMPLOYEE)).status_code, 413)
        with patch.object(settings, "max_image_size_mb", 0):
            self.assertEqual((await self.submit(EMPLOYEE, "n.png", PNG, "image/png")).status_code, 413)
        with patch.object(settings, "max_image_pixels", 10):
            self.assertEqual((await self.submit(EMPLOYEE, "n.png", PNG, "image/png")).status_code, 422)
        with patch.object(settings, "max_pdf_pages", 1):
            self.assertEqual((await self.submit(EMPLOYEE, "p.pdf", pdf_bytes("one", "two"))).status_code, 422)
        self.assertEqual(self.quarantined(), [])
        async with self.session_factory() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(models.DocumentSubmission)), 0)

    async def test_a_user_cannot_fill_the_quarantine(self) -> None:
        with patch.object(settings, "max_pending_submissions_per_user", 2):
            self.assertEqual([(await self.submit(EMPLOYEE)).status_code for _ in range(3)], [201, 201, 429])
            self.assertEqual((await self.submit(FINANCE)).status_code, 201)  # the limit is per user
        self.assertEqual(len(self.quarantined()), 3)

    async def test_a_filename_is_a_label_never_a_path(self) -> None:
        response = await self.submit(EMPLOYEE, "../../etc/passwd.pdf")
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["filename"], "passwd.pdf")
        self.assertEqual(self.quarantined(), [f"{response.json()['id']}.pdf"])
        self.assertEqual((await self.submit(EMPLOYEE, "a" * 300 + ".pdf")).status_code, 422)

    async def test_pending_files_are_not_searchable_and_not_chat_targets_and_not_counted(self) -> None:
        dashboard = lambda: self.client.get("/api/v1/dashboard/overview", headers=self.auth(EMPLOYEE))  # noqa: E731
        before_total = (await dashboard()).json()["documents"]["total"]
        submitted = (await self.submit(EMPLOYEE, "zephyr.pdf")).json()
        # Vector search (the retrieval API) for the exact text: nothing, for the submitter and for the CEO.
        for email in (EMPLOYEE, CEO):
            response = await self.client.post("/api/v1/search/vector", json={"query": "Zephyr migration budget quartz-heron", "top_k": 20}, headers=self.auth(email))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["results"], [])  # nothing is indexed: the pending file has no chunks or vectors
        # A submission is not a document: document chat cannot be pointed at it by its ID.
        chat = await self.client.post("/api/v1/assistant/document-query", json={"document_id": submitted["id"], "query": "What is the budget?"}, headers=self.auth(EMPLOYEE))
        self.assertEqual(chat.status_code, 404)
        self.assertEqual(self.provider.calls, [])
        self.assertEqual((await dashboard()).json()["documents"]["total"], before_total)
        self.assertEqual(await self.documents_titled("zephyr.pdf"), [])


class ReviewTests(ApprovalTestCase):
    async def test_only_the_ceo_sees_the_queue_and_everyone_else_sees_only_their_own(self) -> None:
        ids = {}
        for role, email in ROLE_USERS.items():
            ids[role] = (await self.submit(email, f"{role}.pdf")).json()["id"]
        queue = await self.client.get(f"{SUBMIT}/queue", headers=self.auth(CEO))
        self.assertEqual(queue.status_code, 200)
        self.assertEqual({item["id"] for item in queue.json()["submissions"]}, set(ids.values()))
        item = next(i for i in queue.json()["submissions"] if i["id"] == ids["FINANCE_MANAGER"])
        self.assertEqual((item["submitter"]["email"], item["filename"], item["source_type"]), (FINANCE, "FINANCE_MANAGER.pdf", "pdf"))
        self.assertIsNotNone(item["size_bytes"])
        for role, email in NON_CEO.items():
            self.assertEqual((await self.client.get(f"{SUBMIT}/queue", headers=self.auth(email))).status_code, 403, role)
            mine = await self.client.get(f"{SUBMIT}/mine", headers=self.auth(email))
            self.assertEqual([s["id"] for s in mine.json()["submissions"]], [ids[role]], role)
            self.assertIsNone(mine.json()["submissions"][0]["submitter"])
        self.assertEqual((await self.client.get(f"{SUBMIT}/queue")).status_code, 401)

    async def test_only_the_ceo_can_approve_or_reject_including_the_submitter_themselves(self) -> None:
        submission = (await self.submit(EMPLOYEE)).json()
        before = await self.counts()
        for role, email in NON_CEO.items():
            for action in ("approve", "reject"):
                response = await self.client.post(f"{SUBMIT}/{submission['id']}/{action}", headers=self.auth(email))
                self.assertEqual(response.status_code, 403, (role, action))
        # Client-side flags are not an authorization channel.
        spoof = await self.client.post(f"{SUBMIT}/{submission['id']}/reject", json={"reason": "x", "role": "SUPER_ADMIN", "approved": True}, headers=self.auth(EMPLOYEE))
        self.assertEqual(spoof.status_code, 403)
        self.assertEqual((await self.client.post(f"{SUBMIT}/{submission['id']}/approve")).status_code, 401)
        row = await self.row(submission["id"])
        self.assertEqual((row.status, row.decided_by_user_id, row.document_id), ("pending_approval", None, None))
        self.assertEqual(self.quarantined(), [f"{submission['id']}.pdf"])
        self.assertEqual(await self.counts(), before)

    async def test_preview_is_authenticated_and_limited_to_the_submitter_and_the_ceo(self) -> None:
        content = pdf_bytes("Zephyr migration plan", FACT)
        submission = (await self.submit(EMPLOYEE, "plan.pdf", content)).json()
        for email in (EMPLOYEE, CEO):
            response = await self.client.get(f"{SUBMIT}/{submission['id']}/preview", headers=self.auth(email))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, content)
            self.assertEqual(response.headers["content-type"], "application/pdf")
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")
            self.assertIn("no-store", response.headers["cache-control"])
            self.assertEqual(response.headers["content-disposition"], 'inline; filename="submission-preview.pdf"')
        image = (await self.submit(EMPLOYEE, "n.png", PNG, "image/png")).json()
        shown = await self.client.get(f"{SUBMIT}/{image['id']}/preview", headers=self.auth(CEO))
        self.assertEqual((shown.content, shown.headers["content-type"]), (PNG, "image/png"))
        # Everyone else gets the same answer as for an ID that does not exist.
        missing = await self.client.get(f"{SUBMIT}/{uuid4()}/preview", headers=self.auth(FINANCE))
        for email in (FINANCE, ROLE_USERS["HR_MANAGER"]):
            other = await self.client.get(f"{SUBMIT}/{submission['id']}/preview", headers=self.auth(email))
            self.assertEqual((other.status_code, other.json()["error"]["message"]), (404, NOT_FOUND))
            self.assertEqual(other.json()["error"]["message"], missing.json()["error"]["message"])
            info = await self.client.get(f"{SUBMIT}/{submission['id']}", headers=self.auth(email))
            self.assertEqual(info.status_code, 404)
            self.assertNotIn("plan.pdf", info.text)
        self.assertEqual((await self.client.get(f"{SUBMIT}/{submission['id']}/preview")).status_code, 401)
        # The submitter sees their own record without reviewer-only fields; the CEO sees who submitted it.
        own = await self.client.get(f"{SUBMIT}/{submission['id']}", headers=self.auth(EMPLOYEE))
        self.assertIsNone(own.json()["submitter"])
        review = await self.client.get(f"{SUBMIT}/{submission['id']}", headers=self.auth(CEO))
        self.assertEqual(review.json()["submitter"]["email"], EMPLOYEE)

    async def test_approving_a_pdf_runs_the_real_ingestion_and_grants_only_the_submitter(self) -> None:
        submission = (await self.submit(EMPLOYEE, "zephyr.pdf")).json()
        before = await self.counts()
        response = await self.approve(submission["id"])
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "ready")
        document_id = UUID(body["document_id"])
        after = await self.counts()
        self.assertEqual((after["documents"] - before["documents"], after["user_grants"] - before["user_grants"], after["role_grants"]), (1, 1, before["role_grants"]))
        self.assertGreaterEqual(after["chunks"] - before["chunks"], 2)
        self.assertEqual(after["embedded"] - before["embedded"], after["chunks"] - before["chunks"])  # every chunk indexed
        async with self.session_factory() as session:
            document = await session.get(models.Document, document_id)
            grants = list(await session.scalars(select(models.DocumentUserAccess.user_id).where(models.DocumentUserAccess.document_id == document_id)))
            chunks = list(await session.scalars(select(models.DocumentChunk).where(models.DocumentChunk.document_id == document_id).order_by(models.DocumentChunk.chunk_index)))
        self.assertEqual((document.title, document.source_type, document.owner_user_id), ("zephyr.pdf", "pdf", self.user_id(EMPLOYEE)))
        self.assertEqual(grants, [self.user_id(EMPLOYEE)])  # approval does not widen access
        self.assertEqual([c.page_number for c in chunks], [1, 2])
        self.assertTrue(all(c.embedding_model == lexical_service().model for c in chunks))
        self.assertEqual(self.quarantined(), [])  # the quarantined copy is gone
        self.assertEqual((await self.row(submission["id"])).quarantine_key, None)
        self.assertFalse(body["preview_available"])
        self.assertEqual((await self.client.get(f"{SUBMIT}/{submission['id']}/preview", headers=self.auth(EMPLOYEE))).status_code, 404)

        # Retrieval and document chat now work for the submitter, under the existing grant policy only.
        self.provider.response = LLMResponse("The codename is quartz-heron [S1].", "fake-llm", "stop", 5, 5, provider="groq")
        chat = await self.client.post("/api/v1/assistant/document-query", json={"document_id": str(document_id), "query": "What is the Zephyr codename?"}, headers=self.auth(EMPLOYEE))
        self.assertEqual(chat.status_code, 200, chat.text)
        self.assertEqual({s["document_id"] for s in chat.json()["sources"]}, {str(document_id)})
        self.assertIn("quartz-heron", self.provider.prompts())
        self.provider.calls.clear()
        for email in (FINANCE, CEO):  # no hidden bypass: not even the approver gets access
            denied = await self.client.post("/api/v1/assistant/document-query", json={"document_id": str(document_id), "query": "What is the Zephyr codename?"}, headers=self.auth(email))
            self.assertEqual(denied.status_code, 404, email)
            search = await self.client.post("/api/v1/search/vector", json={"query": "Zephyr quartz-heron", "top_k": 20}, headers=self.auth(email))
            self.assertNotIn(str(document_id), search.text)
        self.assertEqual(self.provider.calls, [])
        mine = await self.client.get(f"{SUBMIT}/mine", headers=self.auth(EMPLOYEE))
        self.assertEqual(mine.json()["submissions"][0]["document_id"], str(document_id))
        # Positive control for the "pending is not searchable" test: the same search finds it once approved.
        found = await self.client.post("/api/v1/search/vector", json={"query": "Zephyr migration budget quartz-heron", "top_k": 20}, headers=self.auth(EMPLOYEE))
        self.assertIn(str(document_id), {r["document_id"] for r in found.json()["results"]})

    async def test_approving_an_image_runs_real_ocr_and_indexes_it(self) -> None:
        submission = (await self.submit(EMPLOYEE, "notice.png", PNG, "image/png")).json()
        response = await self.approve(submission["id"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "ready")
        document_id = UUID(response.json()["document_id"])
        async with self.session_factory() as session:
            chunks = list(await session.scalars(select(models.DocumentChunk).where(models.DocumentChunk.document_id == document_id)))
            document = await session.get(models.Document, document_id)
        self.assertTrue(chunks)
        self.assertEqual((document.source_type, {c.source_locator for c in chunks}, {c.page_number for c in chunks}), ("image", {"image:ocr"}, {None}))
        self.assertIn("cafeteria", " ".join(c.content for c in chunks).lower())  # OCR really read the image
        self.assertTrue(all(c.embedding is not None for c in chunks))
        self.assertEqual(self.quarantined(), [])

    async def test_rejecting_deletes_the_file_and_creates_nothing(self) -> None:
        submission = (await self.submit(EMPLOYEE, "zephyr.pdf")).json()
        before = await self.counts()
        response = await self.reject(submission["id"], reason="Contains personal data")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["status"], body["rejection_reason"], body["document_id"], body["preview_available"]), ("rejected", "Contains personal data", None, False))
        self.assertEqual(self.quarantined(), [])
        self.assertEqual(await self.counts(), before)
        self.assertEqual(await self.documents_titled("zephyr.pdf"), [])
        row = await self.row(submission["id"])
        self.assertEqual((row.status, row.decided_by_user_id, row.quarantine_key), ("rejected", self.user_id(CEO), None))
        self.assertIsNotNone(row.decided_at)
        mine = await self.client.get(f"{SUBMIT}/mine", headers=self.auth(EMPLOYEE))
        self.assertEqual((mine.json()["submissions"][0]["status"], mine.json()["submissions"][0]["rejection_reason"]), ("rejected", "Contains personal data"))
        self.assertEqual((await self.client.get(f"{SUBMIT}/{submission['id']}/preview", headers=self.auth(CEO))).status_code, 404)
        self.assertEqual((await self.reject(submission["id"])).status_code, 200)  # repeat is harmless
        self.assertEqual((await self.approve(submission["id"])).status_code, 409)  # a rejected file can never be ingested
        self.assertEqual(await self.counts(), before)
        queue = await self.client.get(f"{SUBMIT}/queue", headers=self.auth(CEO))
        self.assertNotIn(submission["id"], queue.text)
        # The reason is private to the submitter and the CEO.
        self.assertEqual((await self.client.get(f"{SUBMIT}/{submission['id']}", headers=self.auth(FINANCE))).status_code, 404)

    async def test_repeated_and_concurrent_approvals_create_one_document(self) -> None:
        submission = (await self.submit(EMPLOYEE, "zephyr.pdf")).json()
        before = await self.counts()
        responses = await asyncio.gather(*(self.approve(submission["id"]) for _ in range(4)))
        statuses = sorted(r.status_code for r in responses)
        self.assertEqual(statuses.count(200), 1, statuses)  # exactly one approval did the work
        self.assertTrue(all(code in (200, 409) for code in statuses), statuses)
        again = await self.approve(submission["id"])  # a later repeat reports the finished state
        self.assertEqual((again.status_code, again.json()["status"]), (200, "ready"))
        documents = await self.documents_titled("zephyr.pdf")
        self.assertEqual(len(documents), 1)
        after = await self.counts()
        self.assertEqual(after["documents"] - before["documents"], 1)
        self.assertEqual(after["user_grants"] - before["user_grants"], 1)
        self.assertEqual(after["embedded"] - before["embedded"], after["chunks"] - before["chunks"])
        async with self.session_factory() as session:
            indexes = list(await session.scalars(select(models.DocumentChunk.chunk_index).where(models.DocumentChunk.document_id == documents[0].id)))
        self.assertEqual(sorted(indexes), list(range(len(indexes))))  # no duplicate chunks
        self.assertEqual((await self.row(submission["id"])).attempts, 1)


class FailureTests(ApprovalTestCase):
    async def test_an_indexing_failure_leaves_nothing_active_and_a_retry_path(self) -> None:
        submission = (await self.submit(EMPLOYEE, "zephyr.pdf")).json()
        before, files_before = await self.counts(), self.active_files()

        async def failing_embed(**kwargs):  # noqa: ANN003, ANN202
            from app.services.embeddings.storage import IngestEmbeddingResult

            return IngestEmbeddingResult("failed", None)

        with patch("app.services.submissions.service.embed_ingested_document", side_effect=failing_embed):
            response = await self.approve(submission["id"])
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "failed")
        self.assertIn("could not be indexed", body["failure_message"])
        self.assertIsNone(body["document_id"])
        self.assertEqual(await self.counts(), before)  # no partial document, chunk, embedding or grant
        self.assertEqual(self.active_files(), files_before)  # and no stored copy of one
        self.assertEqual(self.quarantined(), [f"{submission['id']}.pdf"])  # the file is kept for the retry
        self.assertTrue(body["preview_available"])
        queue = await self.client.get(f"{SUBMIT}/queue", headers=self.auth(CEO))
        self.assertEqual([i["status"] for i in queue.json()["submissions"]], ["failed"])
        mine = await self.client.get(f"{SUBMIT}/mine", headers=self.auth(EMPLOYEE))
        self.assertEqual(mine.json()["submissions"][0]["status"], "failed")  # never "ready"
        # Retry through the same endpoint now that indexing works.
        retried = await self.approve(submission["id"])
        self.assertEqual((retried.status_code, retried.json()["status"]), (200, "ready"))
        self.assertEqual(retried.json()["attempts"], 2)
        self.assertEqual(len(await self.documents_titled("zephyr.pdf")), 1)
        self.assertEqual(self.quarantined(), [])

    async def test_unexpected_errors_are_safe_and_clean_up_the_partial_document(self) -> None:
        submission = (await self.submit(EMPLOYEE, "zephyr.pdf")).json()
        before = await self.counts()
        from app.services.pdf import ingestion

        real = ingestion.persist_document

        async def persist_then_crash(**kwargs):  # noqa: ANN003, ANN202
            await real(**kwargs)  # the document, chunks and grant exist ...
            raise RuntimeError("boom at /secret/internal/path with password=hunter2")  # ... then something breaks

        with patch("app.services.pdf.ingestion.persist_document", side_effect=persist_then_crash), self.assertLogs("app", "WARNING"):
            response = await self.approve(submission["id"])
        body = response.json()
        self.assertEqual((response.status_code, body["status"]), (200, "failed"))
        for secret in ("boom", "/secret", "hunter2", "Traceback"):
            self.assertNotIn(secret, response.text)
        self.assertEqual(await self.counts(), before)  # exactly that attempt's rows were removed
        self.assertEqual(self.quarantined(), [f"{submission['id']}.pdf"])
        self.assertEqual((await self.approve(submission["id"])).json()["status"], "ready")

    async def test_ocr_failures_are_safe_and_retryable(self) -> None:
        submission = (await self.submit(EMPLOYEE, "notice.png", PNG, "image/png")).json()
        before = await self.counts()
        with patch("app.services.submissions.service.ingest_image", side_effect=OCRFailedError("engine crashed")):
            body = (await self.approve(submission["id"])).json()
        self.assertEqual((body["status"], body["failure_message"]), ("failed", "The OCR engine failed on this image."))
        self.assertEqual(await self.counts(), before)
        self.assertEqual(len(self.quarantined()), 1)
        self.assertEqual((await self.approve(submission["id"])).json()["status"], "ready")

    async def test_a_missing_quarantine_file_cannot_be_approved_but_can_be_rejected(self) -> None:
        submission = (await self.submit(EMPLOYEE)).json()
        (Path(self.quarantine.name) / f"{submission['id']}.pdf").unlink()
        body = (await self.approve(submission["id"])).json()
        self.assertEqual((body["status"], body["document_id"]), ("failed", None))
        self.assertEqual((await self.reject(submission["id"])).json()["status"], "rejected")

    async def test_a_crashed_attempt_is_cleaned_before_the_next_one_so_no_duplicate_appears(self) -> None:
        submission = (await self.submit(EMPLOYEE, "zephyr.pdf")).json()
        leftover = uuid4()
        # Simulate a process that died mid-approval: the document exists, the submission is stuck in "indexing".
        await ingest_pdf(
            filename="zephyr.pdf", content_type="application/pdf", content=pdf_bytes("Zephyr migration plan", FACT),
            chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap, session_factory=self.session_factory,
            document_id=leftover, owner_user_id=self.user_id(EMPLOYEE),
        )
        async with self.session_factory() as session:
            await session.execute(
                update(models.DocumentSubmission).where(models.DocumentSubmission.id == UUID(submission["id"]))
                .values(status="indexing", attempt_document_id=leftover, updated_at=text("now() - interval '1 hour'"))
            )
            await session.commit()
        fresh = await self.client.post(f"{SUBMIT}/{submission['id']}/approve", headers=self.auth(CEO))
        self.assertEqual((fresh.status_code, fresh.json()["status"]), (200, "ready"))
        documents = await self.documents_titled("zephyr.pdf")
        self.assertEqual([d.id for d in documents], [UUID(fresh.json()["document_id"])])  # the leftover is gone
        self.assertNotEqual(documents[0].id, leftover)

    async def test_an_attempt_that_is_still_running_is_not_taken_over(self) -> None:
        submission = (await self.submit(EMPLOYEE)).json()
        async with self.session_factory() as session:
            await session.execute(update(models.DocumentSubmission).where(models.DocumentSubmission.id == UUID(submission["id"])).values(status="indexing", attempt_document_id=uuid4()))
            await session.commit()
        self.assertEqual((await self.approve(submission["id"])).status_code, 409)
        self.assertEqual((await self.reject(submission["id"])).status_code, 409)  # nor can it be rejected mid-way


class PermissionAndIsolationTests(ApprovalTestCase):
    async def test_permissions_are_exactly_submit_for_all_and_approve_for_the_ceo(self) -> None:
        async with self.session_factory() as session:
            rows = (await session.execute(
                select(models.Role.name, models.Permission.action)
                .join(models.RolePermission, models.RolePermission.role_id == models.Role.id)
                .join(models.Permission, models.Permission.id == models.RolePermission.permission_id)
                .where(models.Permission.resource == "documents", models.Permission.action.in_(["submit", "approve"]))
            )).all()
        granted = {(role, action) for role, action in rows if role in ROLE_USERS}
        self.assertEqual({r for r, a in granted if a == "submit"}, set(ROLE_USERS))
        self.assertEqual({r for r, a in granted if a == "approve"}, {"SUPER_ADMIN"})
        for role, email in ROLE_USERS.items():
            me = await self.client.get("/api/v1/auth/me", headers=self.auth(email))
            permissions = set(me.json()["permissions"])
            self.assertIn("documents:submit", permissions, role)
            self.assertEqual("documents:approve" in permissions, role == "SUPER_ADMIN", role)
        self.assertEqual({p.key for p in PERMISSIONS if p.action in ("submit", "approve")}, {"documents:submit", "documents:approve"})
        self.assertEqual([r.name for r in ROLES if "documents:approve" in r.permissions], ["SUPER_ADMIN"])

    async def test_the_direct_ingestion_endpoints_still_need_documents_write(self) -> None:
        for role, email in NON_CEO.items():
            pdf = await self.client.post("/api/v1/documents/ingest", files={"file": ("a.pdf", pdf_bytes("x"), "application/pdf")}, headers=self.auth(email))
            image = await self.client.post("/api/v1/documents/ingest-image", files={"file": ("n.png", PNG, "image/png")}, headers=self.auth(email))
            self.assertEqual((pdf.status_code, image.status_code), (403, 403), role)
            preview = await self.client.post("/api/v1/documents/preview", files={"file": ("a.pdf", pdf_bytes("x"), "application/pdf")}, headers=self.auth(email))
            self.assertEqual(preview.status_code, 403, role)
        self.assertEqual(self.quarantined(), [])

    async def test_the_workflow_leaves_existing_demo_data_unchanged(self) -> None:
        async def demo_state() -> tuple:
            async with self.session_factory() as session:
                docs = (await session.execute(select(models.Document.id, models.Document.title, models.Document.status).order_by(models.Document.id))).all()
                chunks = await session.scalar(select(func.count()).select_from(models.DocumentChunk))
                grants = (await session.execute(select(models.DocumentRoleAccess.document_id, models.DocumentRoleAccess.role_id))).all()
                users = await session.scalar(select(func.count()).select_from(models.User))
            return [tuple(d) for d in docs], chunks, sorted(map(tuple, grants), key=str), users

        before = await demo_state()
        kept, rejected = (await self.submit(EMPLOYEE, "kept.pdf")).json(), (await self.submit(FINANCE, "dropped.pdf")).json()
        await self.reject(rejected["id"])
        await self.approve(kept["id"])
        after = await demo_state()
        self.assertEqual([d for d in after[0] if d[1] != "kept.pdf"], before[0])  # every earlier document untouched
        self.assertEqual((after[2], after[3]), (before[2], before[3]))  # role grants and users unchanged
        self.assertGreater(after[1], before[1])  # only the approved file added chunks

    def test_quarantine_keys_cannot_name_a_path_and_the_directory_is_apart_from_active_storage(self) -> None:
        for key in ("../x.pdf", "/etc/passwd", "a.pdf", f"{uuid4()}.exe", f"{uuid4()}.pdf/../../x", f"{uuid4()}.pdf\x00"):
            with self.subTest(key=key), self.assertRaises(storage.QuarantineError):
                storage.read(key, limit=10)
        self.assertNotEqual(Path(settings.quarantine_storage_path).resolve(), Path(settings.document_storage_path).resolve())
        self.assertNotIn(Path(settings.document_storage_path).resolve(), Path(settings.quarantine_storage_path).resolve().parents)

    def test_the_migration_permission_ids_match_the_demo_dataset(self) -> None:
        import importlib.util

        path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "d4a7f1c8e2b5_add_document_approval.py"
        spec = importlib.util.spec_from_file_location("approval_migration", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        keyed = {p.key: p.id for p in PERMISSIONS}
        for resource, action, _description, roles in module._PERMISSIONS:
            self.assertEqual(module._permission_id(resource, action), keyed[f"{resource}:{action}"])
            self.assertEqual(set(roles), {r.name for r in ROLES if f"{resource}:{action}" in r.permissions})


if __name__ == "__main__":
    unittest.main()
