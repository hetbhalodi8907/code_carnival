"""Explicit "access_denied" status for POST /api/v1/assistant/query.

Real authentication, real authorization (SQL), real context builder and generator over the demo
dataset in rag_system_test with offline lexical embeddings. Only the LLM is fake: it records the
exact prompt, so each test can prove what the model was (and was not) allowed to see. No live
Groq, LM Studio or embedding-model call is made.
"""

import json
import unittest
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import select

from app import models
from app.services.llm.provider import LLMProvider, LLMProviderRateLimitError, LLMResponse
from app.services.rag.access_denial import (
    ACCESS_DENIED_ANSWER,
    AccessDenialProbe,
    restricted_distance_statement,
)
from app.services.rag.context import ContextBuilder
from app.services.rag.generation import INSUFFICIENT_CONTEXT_ANSWER, INSUFFICIENT_CONTEXT_MARKER, AnswerGenerator
from app.services.vector_search import VectorSearchService
from demo_fixtures import DemoDatasetTestCase, lexical_service
from test_assistant_api import FailingEmbeddings


PATH = "/api/v1/assistant/query"
HR_MANAGER = "meera.iyer@nexora.example"
FINANCE_MANAGER = "vikram.nair@nexora.example"
KABIR = "kabir.sethi@nexora.example"
HR_QUESTION = "What are the confidential HR salary bands and escalation process?"
FINANCE_QUESTION = "What is the Finance department budget?"
RESPONSE_FIELDS = {"status", "answer", "request_id", "sources", "unverified_source_numbers",
                   "rejected_source_numbers", "citation_check"}


class RecordingProvider(LLMProvider):
    def __init__(self) -> None:
        self.answer = INSUFFICIENT_CONTEXT_MARKER
        self.error: Exception | None = None
        self.prompts: list[str] = []

    @property
    def model(self) -> str:
        return "fake-llm"

    async def generate(self, messages, *, temperature=None, max_tokens=None):  # noqa: ANN001
        self.prompts.append("\n".join(message.content for message in messages))
        if self.error is not None:
            raise self.error
        return LLMResponse(self.answer, "fake-llm", "stop", 10, 5)


class AccessDenialApiTests(DemoDatasetTestCase):
    EMBED = True

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.provider = RecordingProvider()
        self.probe_calls = 0
        self.probe_embeddings = lexical_service()

        def make_builder(session_factory):  # noqa: ANN001
            embeddings = lexical_service()
            search = VectorSearchService(
                session_factory, embedding_dimension=embeddings.dimension, embedding_model=embeddings.model
            )
            return ContextBuilder(search, embeddings)

        def make_probe(session_factory):  # noqa: ANN001
            probe = AccessDenialProbe(session_factory, embedding_service=self.probe_embeddings)
            original = probe.is_denied

            async def counting(*args, **kwargs):  # noqa: ANN002, ANN003
                self.probe_calls += 1
                return await original(*args, **kwargs)

            probe.is_denied = counting  # type: ignore[method-assign]
            return probe

        self.patches = [
            patch("app.api.v1.assistant.create_context_builder", side_effect=make_builder),
            patch("app.api.v1.assistant.create_answer_generator", side_effect=lambda: AnswerGenerator(self.provider)),
            patch("app.api.v1.assistant.create_access_denial_probe", side_effect=make_probe),
        ]
        for active in self.patches:
            active.start()

    async def asyncTearDown(self) -> None:
        for active in reversed(self.patches):
            active.stop()
        await super().asyncTearDown()

    async def ask(self, email: str, question: str, expected_status: int = 200) -> dict:
        status, _, body = await self.request_json(
            "POST", PATH, {"query": question, "top_k": 5}, self.token_headers(self.user_id(email))
        )
        self.assertEqual(status, expected_status, body)
        return body

    async def chunk_texts(self, filename: str) -> list[str]:
        async with self.session_factory() as session:
            return list(await session.scalars(
                select(models.DocumentChunk.content).where(models.DocumentChunk.document_id == self.document_id(filename))
            ))

    # ---- 1. authorized answers are unchanged ----------------------------------------------------

    async def test_authorized_answer_and_sources_are_unchanged_and_never_probed(self) -> None:
        self.provider.answer = "The Finance budget is INR 1.5 crore [S1]."
        body = await self.ask(FINANCE_MANAGER, FINANCE_QUESTION)

        self.assertEqual(body["status"], "answered")
        self.assertEqual(body["answer"], "The Finance budget is INR 1.5 crore [S1].")
        self.assertTrue(body["sources"])
        self.assertTrue(any(source["cited"] for source in body["sources"]))
        self.assertEqual(body["citation_check"], "passed")
        self.assertEqual(self.probe_calls, 0)

    # ---- 2 + 4. a genuine denial, with nothing restricted in the response or the prompt ----------

    async def test_restricted_topics_are_denied_with_no_restricted_metadata_or_model_exposure(self) -> None:
        cases = [(FINANCE_MANAGER, HR_QUESTION, "HR_Policy.pdf"), (KABIR, FINANCE_QUESTION, "Finance_Report.pdf")]
        for email, question, restricted_file in cases:
            with self.subTest(user=email, restricted=restricted_file):
                self.provider.prompts.clear()
                body = await self.ask(email, question)

                self.assertEqual(body["status"], "access_denied")
                self.assertEqual(body["answer"], ACCESS_DENIED_ANSWER)
                self.assertEqual(set(body), RESPONSE_FIELDS)
                self.assertEqual((body["sources"], body["unverified_source_numbers"], body["rejected_source_numbers"]), ([], [], []))
                self.assertEqual(body["citation_check"], "not_applicable")
                serialized = json.dumps(body)
                self.assertNotIn(restricted_file, serialized)
                self.assertNotIn(str(self.document_id(restricted_file)), serialized)
                for text in await self.chunk_texts(restricted_file):
                    self.assertNotIn(text[:80], serialized)
                    # Unauthorized text never reached the model: not for this nor any other request.
                    self.assertNotIn(text, " ".join(self.provider.prompts))
                self.assertNotIn(restricted_file, " ".join(self.provider.prompts))

    async def test_a_user_with_access_is_not_denied(self) -> None:
        self.provider.answer = "Salary bands are described in the HR policy [S1]."
        body = await self.ask(HR_MANAGER, HR_QUESTION)

        self.assertEqual(body["status"], "answered")
        self.assertEqual(self.probe_calls, 0)

    # ---- 3. ordinary unanswerable questions stay "insufficient" ----------------------------------

    async def test_unanswerable_questions_keep_the_insufficient_information_response(self) -> None:
        questions = [
            (FINANCE_MANAGER, "What is the capital of France?"),
            (FINANCE_MANAGER, "What is the Finance budget for FY2031?"),
            (KABIR, "Who won the cricket world cup?"),
            (HR_MANAGER, "What is the Mars colony budget?"),
        ]
        for email, question in questions:
            with self.subTest(question=question):
                body = await self.ask(email, question)
                self.assertEqual((body["status"], body["answer"]), ("insufficient_context", INSUFFICIENT_CONTEXT_ANSWER))
                self.assertEqual(body["sources"], [])
        self.assertEqual(self.probe_calls, len(questions))

    # ---- policy signal: confidential compensation ------------------------------------------------

    async def test_other_employees_compensation_is_denied_by_policy_not_by_similarity(self) -> None:
        self.probe_embeddings = lexical_service()
        # Break the relevance probe: only the deterministic policy check may produce this denial.
        from app.services.embeddings.service import EmbeddingService
        self.probe_embeddings = EmbeddingService(FailingEmbeddings(), dimension=lexical_service().dimension)

        denied = await self.ask(KABIR, "What is Rahul Gupta's revised annual CTC?")
        self.assertEqual((denied["status"], denied["answer"]), ("access_denied", ACCESS_DENIED_ANSWER))
        self.assertEqual(denied["sources"], [])

        # Own compensation and an authorized reader are not denied by the policy rule.
        own = await self.ask(KABIR, "What is my revised annual CTC?")
        self.assertEqual(own["status"], "insufficient_context")
        hr = await self.ask(HR_MANAGER, "What is Rahul Gupta's revised annual CTC?")
        self.assertEqual(hr["status"], "insufficient_context")

    # ---- probe failures degrade to "insufficient", never to errors or to a denial ---------------

    async def test_a_failing_probe_preserves_the_insufficient_response(self) -> None:
        from app.services.embeddings.service import EmbeddingService
        self.probe_embeddings = EmbeddingService(FailingEmbeddings(), dimension=lexical_service().dimension)

        body = await self.ask(FINANCE_MANAGER, HR_QUESTION)

        self.assertEqual(body["status"], "insufficient_context")
        self.assertNotIn("sk-should-not-leak", json.dumps(body))

    # ---- 5. provider errors are not authorization denials ---------------------------------------

    async def test_provider_rate_limit_is_a_429_error_and_never_a_denial(self) -> None:
        self.provider.error = LLMProviderRateLimitError("quota detail that must not leak")

        status, _, body = await self.request_json(
            "POST", PATH, {"query": HR_QUESTION, "top_k": 5}, self.token_headers(self.user_id(FINANCE_MANAGER))
        )

        self.assertEqual(status, 429, body)
        self.assertNotIn("access_denied", json.dumps(body))
        self.assertNotIn("quota detail", json.dumps(body))
        self.assertEqual(self.probe_calls, 0)

    # ---- 6. the caller cannot choose identity or widen access ------------------------------------

    async def test_identity_fields_are_rejected_and_the_denial_follows_the_token(self) -> None:
        status, _, body = await self.request_json(
            "POST", PATH, {"query": HR_QUESTION, "user_id": str(self.user_id(HR_MANAGER)), "role": "SUPER_ADMIN"},
            self.token_headers(self.user_id(FINANCE_MANAGER)),
        )
        self.assertEqual(status, 422, body)
        self.assertEqual(self.provider.prompts, [])

        # The same question: denied for the Finance token, answered for the HR token.
        self.provider.answer = "Salary bands are described in the HR policy [S1]."
        self.assertEqual((await self.ask(HR_MANAGER, HR_QUESTION))["status"], "answered")
        self.provider.answer = INSUFFICIENT_CONTEXT_MARKER
        self.assertEqual((await self.ask(FINANCE_MANAGER, HR_QUESTION))["status"], "access_denied")

        # No token: nothing is returned at all.
        status, _, _ = await self.request_json("POST", PATH, {"query": HR_QUESTION}, {})
        self.assertEqual(status, 401)

    # ---- the probe's SQL returns one number and nothing else -------------------------------------

    async def test_the_probe_statement_selects_only_an_aggregate_number(self) -> None:
        statement = restricted_distance_statement([0.0] * lexical_service().dimension, "any-model", UUID(int=1))

        columns = list(statement.selected_columns)
        self.assertEqual(len(columns), 1)
        self.assertEqual(columns[0].type.__class__.__name__, "Float")
        selected = str(statement.compile()).split("FROM")[0].lower()
        for forbidden in ("content", "title", "source_locator", "document_id", "chunk_index", "id"):
            self.assertNotIn(f"document_chunks.{forbidden}", selected)


if __name__ == "__main__":
    unittest.main()
