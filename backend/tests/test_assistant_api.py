"""Part 6.3: POST /api/v1/assistant/query, end to end with fake LLM providers.

Real authentication, real authorization-aware retrieval over the demo dataset in
rag_system_test (offline lexical embeddings), real ContextBuilder and AnswerGenerator.
Only the LLM provider is fake; no live Groq or OpenAI call is made.
"""

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

from pydantic import SecretStr
from sqlalchemy import select

from app import models
from app.core.config import settings
from app.core.security import create_access_token
from app.main import app
from app.models.document_chunk import EMBEDDING_VECTOR_DIMENSION
from app.schemas.rag import AssistantQueryResponse, MAX_QUERY_LENGTH, TrustProof
from app.services.authorization import load_authenticated_user
from app.services.embeddings.provider import EmbeddingProvider, EmbeddingProviderError
from app.services.embeddings.service import EmbeddingService
from app.services.llm.provider import LLMProvider, LLMProviderError, LLMProviderTimeoutError, LLMResponse
from app.services.rag.context import ContextBuilder
from app.api.v1.assistant import _to_response
from app.services.rag.generation import (
    INSUFFICIENT_CONTEXT_ANSWER,
    NO_CONTEXT_ANSWER,
    AnswerGenerator,
    RagGenerationError,
)
from app.services.vector_search import VectorSearchResult, VectorSearchService
from demo_fixtures import DemoDatasetTestCase, lexical_service
from support import call_app


PATH = "/api/v1/assistant/query"
SUPER_ADMIN = "ishaan.malhotra@nexora.example"
HR_MANAGER = "meera.iyer@nexora.example"
FINANCE_MANAGER = "vikram.nair@nexora.example"
ENGINEERING_MANAGER = "ananya.rao@nexora.example"
SECURITY_MANAGER = "devika.krishnan@nexora.example"
KABIR = "kabir.sethi@nexora.example"
INACTIVE = "farhan.qureshi@nexora.example"
FINANCE_QUESTION = "What is the Finance department budget?"
FAKE_KEY = "gsk_test_placeholder_not_a_real_key"
RESPONSE_FIELDS = {"status", "answer", "request_id", "sources", "unverified_source_numbers",
                   "rejected_source_numbers", "citation_check", "trust_proof"}
SOURCE_FIELDS = {"source_number", "document_id", "document_title", "chunk_id", "page_number",
                 "source_locator", "similarity", "source_type", "cited"}


class FakeLLMProvider(LLMProvider):
    def __init__(self) -> None:
        self.response: object = LLMResponse("The Finance budget is INR 1.5 crore [S1].", "fake-llm", "stop", 90, 9)
        self.error: Exception | None = None
        self.calls: list[tuple] = []

    @property
    def model(self) -> str:
        return "fake-llm"

    async def generate(self, messages, *, temperature=None, max_tokens=None):  # noqa: ANN001
        self.calls.append(tuple(messages))
        if self.error is not None:
            raise self.error
        return self.response


class RecordingContextBuilder(ContextBuilder):
    """The real Part 6.1 builder, recording what it was asked and what it produced."""

    def __init__(self, *args: object, build_for=None, **kwargs: object) -> None:  # noqa: ANN001
        super().__init__(*args, **kwargs)
        self.build_for = build_for  # test hook: build for a different user (inconsistent context)
        self.calls: list[tuple] = []

    async def build(self, query, user, *, request_id=None):  # noqa: ANN001
        context = await super().build(query, self.build_for or user, request_id=request_id)
        self.calls.append((query, user, context))
        return context


class RecordingAnswerGenerator(AnswerGenerator):
    def __init__(self, provider: LLMProvider, error: Exception | None = None) -> None:
        super().__init__(provider)
        self.error = error
        self.calls: list[tuple] = []

    async def generate(self, query, context, *, user, request_id=None):  # noqa: ANN001
        self.calls.append((query, context, user))
        if self.error is not None:
            raise self.error
        return await super().generate(query, context, user=user, request_id=request_id)


class StubSearch:
    def __init__(self, results: list[VectorSearchResult]) -> None:
        self.results = results

    async def search_text(self, query, *, top_k, embedding_service, user_id):  # noqa: ANN001
        return list(self.results)


class FailingEmbeddings(EmbeddingProvider):
    @property
    def model(self) -> str:
        return "test-lexical-embedding"

    async def embed_text(self, text):  # noqa: ANN001
        raise EmbeddingProviderError("provider said: invalid key sk-should-not-leak")

    async def embed_texts(self, texts):  # noqa: ANN001
        raise EmbeddingProviderError("provider said: invalid key sk-should-not-leak")


class BrokenSession:
    """A database session whose queries fail with a message that must never leak."""

    async def execute(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("could not connect to postgresql://postgres:postgres@localhost:5432/rag_system_test")

    async def close(self) -> None:
        return None


class AssistantQueryApiTests(DemoDatasetTestCase):
    EMBED = True

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.provider = FakeLLMProvider()
        self.builders: list[RecordingContextBuilder] = []
        self.generators: list[RecordingAnswerGenerator] = []
        self.builder_options: dict = {}
        self.search_override = None
        self.generator_error: Exception | None = None
        self.patches = [
            patch("app.api.v1.assistant.create_context_builder", side_effect=self.make_builder),
            patch("app.api.v1.assistant.create_answer_generator", side_effect=self.make_generator),
        ]
        for active in self.patches:
            active.start()

    async def asyncTearDown(self) -> None:
        for active in reversed(self.patches):
            active.stop()
        await super().asyncTearDown()

    # ---- wiring ------------------------------------------------------------------------

    def make_builder(self, session_factory) -> RecordingContextBuilder:  # noqa: ANN001
        embedding_service = lexical_service()
        search = self.search_override or VectorSearchService(
            session_factory,
            embedding_dimension=embedding_service.dimension,
            embedding_model=embedding_service.model,
        )
        builder = RecordingContextBuilder(search, self.builder_embeddings(), **self.builder_options)
        self.builders.append(builder)
        return builder

    def builder_embeddings(self) -> EmbeddingService:
        return self.builder_options.pop("embeddings", None) or lexical_service()

    def make_generator(self) -> RecordingAnswerGenerator:
        generator = RecordingAnswerGenerator(self.provider, self.generator_error)
        self.generators.append(generator)
        return generator

    def builds(self) -> list[tuple]:
        return [call for builder in self.builders for call in builder.calls]

    def generations(self) -> list[tuple]:
        return [call for generator in self.generators for call in generator.calls]

    def assertNothingReached(self) -> None:
        self.assertEqual((self.builders, self.generators, self.provider.calls), ([], [], []))

    async def ask(self, headers: dict[str, str], payload: object, path: str = PATH) -> tuple[int, dict, dict]:
        status, response_headers, body = await self.request_json("POST", path, payload, headers)
        return status, response_headers, body

    async def ask_failing(self, headers: dict[str, str], payload: object) -> tuple[int, dict]:
        with self.assertLogs("app", "WARNING") as captured:
            status, _, body = await self.ask(headers, payload)
        logs = "\n".join(captured.output)
        for secret in (FAKE_KEY, "sk-should-not-leak", "postgresql://", FINANCE_QUESTION):
            self.assertNotIn(secret, logs)
        return status, body

    def headers_for(self, email: str) -> dict[str, str]:
        return self.token_headers(self.user_id(email))

    def source_documents(self, body: dict) -> set[str]:
        return {self.filename_of(UUID(source["document_id"])) for source in body["sources"]}

    # ---- A. authentication -----------------------------------------------------------------

    async def test_missing_authentication_is_rejected_before_any_service(self) -> None:
        status, headers, body = await self.ask({}, {"query": FINANCE_QUESTION})
        self.assertEqual(status, 401)
        self.assertEqual(headers["www-authenticate"], "Bearer")
        self.assertEqual(body["error"]["message"], "Authentication is required.")
        self.assertNothingReached()

    async def test_invalid_tokens_are_rejected_before_any_service(self) -> None:
        user_id = self.user_id(FINANCE_MANAGER)
        expired, _ = create_access_token(user_id, now=datetime.now(timezone.utc) - timedelta(days=2))
        with patch.object(settings, "jwt_secret_key", SecretStr("another-secret-that-is-long-enough-123456")):
            forged, _ = create_access_token(user_id)
        for header in ("Bearer not-a-jwt", f"Bearer {expired}", f"Bearer {forged}", "Basic dXNlcjpwYXNz",
                       "Bearer", f"Token {expired}"):
            with self.subTest(header=header[:14]):
                status, _, body = await self.ask({"Authorization": header}, {"query": FINANCE_QUESTION})
                self.assertEqual(status, 401)
                self.assertNotIn("answer", body)
        self.assertNothingReached()

    async def test_inactive_account_token_is_rejected(self) -> None:
        status, _, _ = await self.ask(self.headers_for(INACTIVE), {"query": FINANCE_QUESTION})
        self.assertEqual(status, 401)
        self.assertNothingReached()

    async def test_account_without_documents_read_is_forbidden(self) -> None:
        async with self.session_factory() as session:
            user = models.User(email=f"noread-{uuid4().hex}@example.invalid", full_name="No Read", is_active=True)
            session.add(user)
            await session.commit()
            user_id = user.id
        status, _, body = await self.ask(self.token_headers(user_id), {"query": FINANCE_QUESTION})
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["message"], "You do not have permission to perform this action.")
        self.assertNothingReached()

    async def test_valid_login_token_resolves_the_calling_user(self) -> None:
        status, _, body = await self.ask(await self.login_headers(FINANCE_MANAGER), {"query": FINANCE_QUESTION})
        self.assertEqual(status, 200, body)
        (_, built_for, _), = self.builds()
        self.assertEqual((built_for.id, built_for.email), (self.user_id(FINANCE_MANAGER), FINANCE_MANAGER))
        self.assertIs(self.generations()[0][2], built_for)

    # ---- B. input validation ----------------------------------------------------------------------

    async def test_valid_request_is_trimmed_and_passed_on(self) -> None:
        status, _, _ = await self.ask(self.headers_for(FINANCE_MANAGER), {"query": f"  {FINANCE_QUESTION}  ", "top_k": 3})
        self.assertEqual(status, 200)
        query = self.builds()[0][0]
        self.assertEqual((query.query, query.top_k), (FINANCE_QUESTION, 3))

    async def test_invalid_bodies_are_rejected_before_any_service(self) -> None:
        admin_id = str(self.user_id(SUPER_ADMIN))
        payloads = (
            {"query": ""}, {"query": "   \n "}, {"query": "x" * (MAX_QUERY_LENGTH + 1)}, {"top_k": 5}, {"query": 123},
            {"query": "q", "top_k": 0}, {"query": "q", "top_k": 21}, {"query": "q", "top_k": "5"},
            {"query": "q", "top_k": 5.5}, {"query": "q", "top_k": True}, {"query": "q", "top_k": None},
            {"query": "q", "user_id": admin_id}, {"query": "q", "role": "SUPER_ADMIN"},
            {"query": "q", "roles": ["SUPER_ADMIN"]}, {"query": "q", "permissions": ["documents:read"]},
            {"query": "q", "department": "HR"}, ["What is the budget?"], "What is the budget?",
        )
        headers = self.headers_for(FINANCE_MANAGER)
        for payload in payloads:
            with self.subTest(payload=str(payload)[:60]):
                status, _, body = await self.ask(headers, payload)
                self.assertEqual(status, 422)
                self.assertEqual(body["error"]["code"], "VALIDATION_ERROR")
        status, _, response = await call_app(
            "POST", PATH, headers={**headers, "Content-Type": "application/json"}, body=b"{not json"
        )
        self.assertEqual(status, 422)
        self.assertNothingReached()

    # ---- C. successful pipeline -----------------------------------------------------------------

    async def test_pipeline_passes_one_user_query_and_context_through_and_returns_the_contract(self) -> None:
        status, headers, body = await self.ask(self.headers_for(FINANCE_MANAGER), {"query": FINANCE_QUESTION})
        self.assertEqual(status, 200, body)

        (built_query, built_for, context), = self.builds()
        (gen_query, gen_context, gen_user), = self.generations()
        self.assertIs(gen_query, built_query)
        self.assertIs(gen_context, context)
        self.assertIs(gen_user, built_for)
        self.assertEqual(len(self.provider.calls), 1)

        self.assertEqual(set(body), RESPONSE_FIELDS)
        AssistantQueryResponse.model_validate(body)
        self.assertEqual(body["status"], "answered")
        self.assertEqual(body["answer"], "The Finance budget is INR 1.5 crore [S1].")
        self.assertEqual(body["request_id"], headers["x-request-id"])
        self.assertEqual(body["unverified_source_numbers"], [1])
        self.assertIn("Finance_Report.pdf", self.source_documents(body))
        self.assertEqual(len(body["sources"]), len(context.items))
        for source, item in zip(body["sources"], context.items, strict=True):
            self.assertEqual(set(source), SOURCE_FIELDS)
            self.assertEqual(
                (source["source_number"], UUID(source["document_id"]), source["document_title"],
                 UUID(source["chunk_id"]), source["page_number"], source["source_locator"], source["similarity"]),
                (item.rank, item.document_id, item.document_title, item.chunk_id, item.page_number,
                 item.source_locator, item.similarity),
            )
        # Metadata only: no chunk text is returned.
        for item in context.items:
            self.assertNotIn(item.content, json.dumps(body))

    # ---- D. missing or unauthorized context ------------------------------------------------------

    async def test_no_usable_context_returns_the_fixed_answer_without_an_llm_call(self) -> None:
        blank = VectorSearchResult(
            chunk_id=uuid4(), document_id=uuid4(), document_title="Blank", chunk_index=0, page_number=1,
            source_locator="page:1", content="   ", distance=0.1, similarity=0.9,
        )
        for results in ([], [blank]):
            with self.subTest(results=len(results)):
                self.search_override = StubSearch(results)
                status, _, body = await self.ask(self.headers_for(FINANCE_MANAGER), {"query": "What is the office holiday calendar?"})
                self.assertEqual(status, 200, body)
                self.assertEqual(
                    (body["status"], body["answer"], body["sources"], body["unverified_source_numbers"]),
                    ("no_authorized_context", NO_CONTEXT_ANSWER, [], []),
                )
        self.assertEqual(self.provider.calls, [])

    async def test_insufficient_context_returns_the_fixed_answer_and_no_sources(self) -> None:
        self.provider.response = LLMResponse("INSUFFICIENT_CONTEXT", "m", "stop", 1, 1)
        status, _, body = await self.ask(self.headers_for(FINANCE_MANAGER), {"query": "What is the parental leave?"})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["status"], "insufficient_context")
        self.assertEqual(body["answer"], INSUFFICIENT_CONTEXT_ANSWER)
        self.assertEqual((body["sources"], body["unverified_source_numbers"]), ([], []))
        self.assertEqual(len(self.provider.calls), 1)

    async def test_unauthorized_documents_never_reach_generation_or_the_response(self) -> None:
        cases = (
            (FINANCE_MANAGER, "HR salary bands promotion merit increase", "HR_Policy.pdf"),
            (KABIR, "Rahul Gupta revised annual CTC compensation statement", "Compensation_Statement_Rahul_Gupta.pdf"),
            (ENGINEERING_MANAGER, "information security policy incident classification", "Security_Policy.pdf"),
        )
        for email, question, forbidden in cases:
            with self.subTest(user=email):
                status, _, body = await self.ask(self.headers_for(email), {"query": question, "top_k": 20})
                self.assertEqual(status, 200, body)
                context = self.generations()[-1][1]
                self.assertNotIn(forbidden, {self.filename_of(item.document_id) for item in context.items})
                self.assertNotIn(forbidden, self.source_documents(body))
                self.assertLessEqual(self.source_documents(body), self.expected_documents(email))
                self.assertNotIn(str(self.document_id(forbidden)), json.dumps(body))
                prompt = "\n".join(message.content for message in self.provider.calls[-1])
                async with self.session_factory() as session:
                    for text in await session.scalars(
                        select(models.DocumentChunk.content).where(
                            models.DocumentChunk.document_id == self.document_id(forbidden)
                        )
                    ):
                        self.assertNotIn(text, prompt)

    # ---- E. security ----------------------------------------------------------------------------

    async def test_client_identity_hints_cannot_override_the_token(self) -> None:
        admin_id = str(self.user_id(SUPER_ADMIN))
        headers = {**self.headers_for(FINANCE_MANAGER), "X-User-Id": admin_id, "X-Role": "SUPER_ADMIN"}
        status, _, body = await self.ask(
            headers, {"query": "HR salary bands and the Finance budget", "top_k": 20},
            path=f"{PATH}?user_id={admin_id}&role=SUPER_ADMIN",
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(self.builds()[0][1].id, self.user_id(FINANCE_MANAGER))
        self.assertLessEqual(self.source_documents(body), self.expected_documents(FINANCE_MANAGER))
        self.assertNotIn("HR_Policy.pdf", self.source_documents(body))

    async def test_each_role_is_answered_as_itself_from_its_own_documents(self) -> None:
        for email in (SUPER_ADMIN, HR_MANAGER, FINANCE_MANAGER, ENGINEERING_MANAGER, SECURITY_MANAGER, KABIR):
            with self.subTest(user=email):
                status, _, body = await self.ask(self.headers_for(email), {"query": FINANCE_QUESTION, "top_k": 20})
                self.assertEqual(status, 200, body)
                _, built_for, context = self.builds()[-1]
                self.assertEqual(built_for.id, self.user_id(email))  # never an admin or service identity
                self.assertEqual(context.user_id, self.user_id(email))
                self.assertLessEqual(self.source_documents(body), self.expected_documents(email))

    async def test_model_references_are_returned_only_as_unverified_numbers(self) -> None:
        fabricated_chunk = "11111111-1111-4111-8111-111111111111"
        self.provider.response = LLMResponse(
            f"The budget is INR 99 crore [S7] (chunk {fabricated_chunk}, page 42) [S1].", "m", "stop", 1, 1
        )
        status, _, body = await self.ask(self.headers_for(FINANCE_MANAGER), {"query": FINANCE_QUESTION, "top_k": 5})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["unverified_source_numbers"], [1])  # S7 matches no retrieved source
        self.assertEqual((body["rejected_source_numbers"], body["citation_check"]), ([7], "partial"))
        self.assertNotIn("[S7]", body["answer"])
        self.assertEqual([s["cited"] for s in body["sources"]][:2], [True, False])
        self.assertNotIn("citations", body)
        self.assertEqual([source["source_number"] for source in body["sources"]], [1, 2, 3, 4, 5])
        self.assertNotIn(fabricated_chunk, json.dumps(body["sources"]))
        self.assertNotIn(42, [source["page_number"] for source in body["sources"]])
        schema = app.openapi()["components"]["schemas"]["AssistantQueryResponse"]["properties"]
        self.assertIn("NOT verified", schema["unverified_source_numbers"]["description"])
        self.assertIn("not a validated citation",
                      app.openapi()["components"]["schemas"]["AssistantSource"]["description"])

    async def test_failures_never_return_internal_details(self) -> None:
        self.provider.error = LLMProviderError(f"401 invalid key {FAKE_KEY}")
        status, body = await self.ask_failing(self.headers_for(FINANCE_MANAGER), {"query": FINANCE_QUESTION})
        self.assertEqual(status, 502)
        text = json.dumps(body)
        context = self.generations()[0][1]
        for leaked in (FAKE_KEY, FINANCE_QUESTION, "Traceback", "SOURCES", "Use only the SOURCES", context.boundary,
                       *(item.content for item in context.items)):
            self.assertNotIn(leaked, text)
        self.assertEqual(set(body), {"error"})

    # ---- F. failures ---------------------------------------------------------------------------------

    async def test_provider_failures_map_to_gateway_errors_never_answers(self) -> None:
        cases = (
            (LLMProviderError("boom"), None, 502, "The language model request failed."),
            (LLMProviderTimeoutError("slow"), None, 504, "The language model did not respond in time."),
            (None, LLMResponse("   ", "m", "stop", 1, 0), 502, "The language model returned an empty answer."),
            (None, LLMResponse("Budget is INR", "m", "length", 1, 1024), 502,
             "The language model's answer was incomplete."),
            (None, "not a response object", 502, "The language model returned an invalid answer."),
        )
        for error, response, expected_status, message in cases:
            with self.subTest(message=message):
                self.provider.error, self.provider.response = error, response
                status, body = await self.ask_failing(self.headers_for(FINANCE_MANAGER), {"query": FINANCE_QUESTION})
                self.assertEqual(status, expected_status)
                self.assertEqual(body["error"]["message"], message)
                self.assertNotIn("answer", body)

    async def test_generation_failure_categories_map_to_stable_statuses(self) -> None:
        expected = {"invalid_context": 500, "unsafe_prompt": 422, "provider_timeout": 504, "provider_rate_limited": 429, "provider_error": 502,
                    "empty_output": 502, "incomplete_output": 502, "invalid_output": 502}
        for category, expected_status in expected.items():
            with self.subTest(category=category):
                self.generator_error = RagGenerationError(category)
                status, body = await self.ask_failing(self.headers_for(FINANCE_MANAGER), {"query": FINANCE_QUESTION})
                self.assertEqual(status, expected_status)
                self.assertEqual(body["error"]["message"], str(RagGenerationError(category)))

    async def test_inconsistent_context_is_a_safe_500_without_an_llm_call(self) -> None:
        async with self.session_factory() as session:
            admin = await load_authenticated_user(session, self.user_id(SUPER_ADMIN))
        self.builder_options = {"build_for": admin}  # a context for someone else must be refused
        status, body = await self.ask_failing(self.headers_for(FINANCE_MANAGER), {"query": FINANCE_QUESTION})
        self.assertEqual(status, 500)
        self.assertEqual(body["error"]["message"], "The retrieval context is not valid for this request.")
        self.assertEqual(self.provider.calls, [])

    async def test_retrieval_database_failure_is_a_safe_503(self) -> None:
        embedding_service = lexical_service()
        self.search_override = VectorSearchService(
            lambda: BrokenSession(),  # type: ignore[arg-type, return-value]
            embedding_dimension=embedding_service.dimension,
            embedding_model=embedding_service.model,
        )
        status, body = await self.ask_failing(self.headers_for(FINANCE_MANAGER), {"query": FINANCE_QUESTION})
        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["message"], "Vector search failed.")
        self.assertNotIn("postgresql", json.dumps(body))
        self.assertEqual((self.generations(), self.provider.calls), ([], []))

    async def test_embedding_failures_are_reported_without_generation(self) -> None:
        self.builder_options = {"embeddings": EmbeddingService(FailingEmbeddings(), dimension=EMBEDDING_VECTOR_DIMENSION)}
        status, body = await self.ask_failing(self.headers_for(FINANCE_MANAGER), {"query": FINANCE_QUESTION})
        self.assertEqual(status, 502)
        self.assertEqual(body["error"]["message"], "The embedding provider could not generate embeddings.")
        self.assertNotIn("sk-should-not-leak", json.dumps(body))
        self.assertEqual(self.generations(), [])

        self.patches[0].stop()  # the real factory, with an unusable provider selected
        try:
            with patch.object(settings, "embedding_provider", "openai"), patch.object(settings, "openai_api_key", None):
                status, body = await self.ask_failing(self.headers_for(FINANCE_MANAGER), {"query": FINANCE_QUESTION})
        finally:
            self.patches[0].start()
        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["message"], "The embedding provider is not configured.")
        self.assertEqual((self.generations(), self.provider.calls), ([], []))

    async def test_missing_llm_configuration_fails_before_retrieval(self) -> None:
        self.patches[1].stop()  # the real generator factory
        try:
            with patch.object(settings, "groq_api_key", None):
                status, body = await self.ask_failing(self.headers_for(FINANCE_MANAGER), {"query": FINANCE_QUESTION})
        finally:
            self.patches[1].start()
        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["message"], "The language model is not configured.")
        self.assertEqual(self.builders, [])

    async def test_unexpected_errors_return_a_generic_500(self) -> None:
        self.generator_error = RuntimeError(f"boom {FAKE_KEY}")
        with self.assertLogs("app.exceptions", "ERROR"):
            status, _, body = await self.ask(self.headers_for(FINANCE_MANAGER), {"query": FINANCE_QUESTION})
        self.assertEqual(status, 500)
        self.assertEqual(body["error"]["message"], "An unexpected error occurred.")
        self.assertNotIn(FAKE_KEY, json.dumps(body))

    # ---- G. contract and regression -----------------------------------------------------------------

    # ---- TrustProof receipt -------------------------------------------------------------------------------

    async def test_an_answer_carries_a_trust_proof_backed_by_the_executed_route(self) -> None:
        self.provider.response = LLMResponse("The Finance budget is INR 1.5 crore [S1].", "qwen/qwen3.5-9b", "stop", 90, 9, provider="lm_studio")
        status, _, body = await self.ask(self.headers_for(FINANCE_MANAGER), {"query": FINANCE_QUESTION})
        self.assertEqual(status, 200, body)
        self.assertEqual(
            body["trust_proof"],
            {"authorization": "access_controlled_retrieval", "authorized_source_count": len(body["sources"]),
             "provider": "lm_studio", "model": "qwen/qwen3.5-9b"},
        )
        self.assertGreater(len(body["sources"]), 0)
        self.assertEqual(body["citation_check"], "passed")
        TrustProof.model_validate(body["trust_proof"])
        # The receipt is metadata only: no prompt, completion, passage text or identifiers.
        serialized = json.dumps(body["trust_proof"])
        for item in self.generations()[-1][1].items:
            self.assertNotIn(item.content[:60], serialized)
            self.assertNotIn(str(item.document_id), serialized)
        self.assertNotIn(body["answer"], serialized)

    async def test_the_receipt_counts_only_the_final_sources_returned(self) -> None:
        status, _, body = await self.ask(self.headers_for(KABIR), {"query": "What is the code review process?", "top_k": 2})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["trust_proof"]["authorized_source_count"], len(body["sources"]))
        self.assertLessEqual(len(body["sources"]), 2)

    async def test_partial_citations_are_reported_honestly_and_an_unknown_provider_stays_unknown(self) -> None:
        self.provider.response = LLMResponse("Budget is INR 1.5 crore [S1] and also [S9].", "fake-llm", "stop", 90, 9)
        status, _, body = await self.ask(self.headers_for(FINANCE_MANAGER), {"query": FINANCE_QUESTION})
        self.assertEqual(status, 200, body)
        self.assertEqual((body["citation_check"], body["rejected_source_numbers"]), ("partial", [9]))
        self.assertEqual((body["trust_proof"]["provider"], body["trust_proof"]["model"]), (None, "fake-llm"))  # not guessed

    async def test_no_receipt_unless_the_answer_was_generated(self) -> None:
        self.provider.response = LLMResponse("INSUFFICIENT_CONTEXT", "m", "stop", 1, 1)
        _, _, insufficient = await self.ask(self.headers_for(FINANCE_MANAGER), {"query": "What is the parental leave?"})
        self.assertEqual((insufficient["status"], insufficient["trust_proof"]), ("insufficient_context", None))
        self.search_override = StubSearch([])
        _, _, nothing = await self.ask(self.headers_for(FINANCE_MANAGER), {"query": "What is the office holiday calendar?"})
        self.assertEqual((nothing["status"], nothing["trust_proof"]), ("no_authorized_context", None))

    async def test_a_failed_request_returns_an_error_envelope_never_a_receipt(self) -> None:
        for error in (LLMProviderError("boom"), LLMProviderTimeoutError("slow")):
            self.provider.error = error
            status, body = await self.ask_failing(self.headers_for(FINANCE_MANAGER), {"query": FINANCE_QUESTION})
            self.assertGreaterEqual(status, 500)
            self.assertNotIn("trust_proof", body)
            self.assertNotIn("answer", body)

    async def test_authorization_is_not_claimed_for_a_context_built_for_someone_else(self) -> None:
        self.provider.response = LLMResponse("Budget [S1].", "m", "stop", 1, 1, provider="groq")
        await self.ask(self.headers_for(FINANCE_MANAGER), {"query": FINANCE_QUESTION})
        (query, context, user), = self.generations()
        result = await AnswerGenerator(self.provider).generate(query, context, user=user)
        self.assertEqual(_to_response(result, "rid", user).trust_proof.authorization, "access_controlled_retrieval")
        async with self.session_factory() as session:
            stranger = await load_authenticated_user(session, self.user_id(KABIR))
        self.assertIsNone(_to_response(result, "rid", stranger).trust_proof)  # context.user_id != caller: no claim

    async def test_openapi_documents_only_the_authenticated_post_endpoint(self) -> None:
        spec = app.openapi()
        self.assertEqual(
            set(spec["paths"]),
            {"/", "/api/v1/health", "/api/v1/ready", "/api/v1/auth/login", "/api/v1/auth/me",
             "/api/v1/documents/preview", "/api/v1/documents/ingest", "/api/v1/documents/ingest-image",
             "/api/v1/embeddings/documents/{document_id}",
             "/api/v1/search/vector", "/api/v1/dashboard/overview", "/api/v1/assistant/document-query",
             "/api/v1/document-submissions", "/api/v1/document-submissions/mine", "/api/v1/document-submissions/queue",
             "/api/v1/document-submissions/{submission_id}", "/api/v1/document-submissions/{submission_id}/preview",
             "/api/v1/document-submissions/{submission_id}/approve", "/api/v1/document-submissions/{submission_id}/reject", PATH},
        )
        operation = spec["paths"][PATH]
        self.assertEqual(list(operation), ["post"])
        post = operation["post"]
        self.assertEqual(post["security"], [{"BearerAuth": []}])
        self.assertEqual(post["requestBody"]["content"]["application/json"]["schema"]["$ref"],
                         "#/components/schemas/RagQuery")
        self.assertEqual(post["responses"]["200"]["content"]["application/json"]["schema"]["$ref"],
                         "#/components/schemas/AssistantQueryResponse")
        self.assertLessEqual({"401", "403", "422", "500", "502", "503", "504"}, set(post["responses"]))
        required = set(spec["components"]["schemas"]["AssistantQueryResponse"]["required"])
        self.assertLessEqual(required, RESPONSE_FIELDS)
        # The original contract fields stay required; the additions are optional for older clients.
        self.assertLessEqual({"status", "answer", "request_id", "sources", "unverified_source_numbers"}, required)

        status, _, _ = await call_app("GET", PATH, headers=self.headers_for(FINANCE_MANAGER))
        self.assertEqual(status, 405)

    async def test_existing_endpoints_still_work(self) -> None:
        status, _, _ = await call_app("GET", "/api/v1/health")
        self.assertEqual(status, 200)
        headers = await self.login_headers(KABIR)
        status, _, me = await self.request_json("GET", "/api/v1/auth/me", headers=headers)
        self.assertEqual((status, me["email"]), (200, KABIR))
        with patch("app.api.v1.embeddings.create_embedding_service", return_value=lexical_service()):
            status, _, found = await self.request_json(
                "POST", "/api/v1/search/vector", {"query": "compensation statement", "top_k": 5}, headers
            )
        self.assertEqual(status, 200)
        self.assertNotIn("document_title", found["results"][0])  # the search contract is unchanged


if __name__ == "__main__":
    unittest.main()
