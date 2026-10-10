"""LLM_PROVIDER=lm_studio (local-only): mocked clients only (no Groq, no LM Studio, no network)."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import openai
from pydantic import SecretStr
from sqlalchemy import select

from app import models
from app.core.config import Settings, settings
from app.schemas.rag import RagQuery
from app.services.llm.provider import (
    ChatMessage,
    FallbackLLMProvider,
    LLMConfigurationError,
    LLMProviderError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
    OpenAICompatibleLLMProvider,
    create_llm_provider,
)
from app.services.rag.generation import AnswerGenerator, RagGenerationError
from demo_fixtures import DemoDatasetTestCase
from test_assistant_api import FINANCE_MANAGER, FINANCE_QUESTION, PATH, RecordingContextBuilder
from test_rag_generation import FINANCE_RESULTS, QUESTION, build_context, make_user


REQUEST = httpx.Request("POST", "http://127.0.0.1:1235/v1/chat/completions")
MESSAGES = [ChatMessage("system", "Be brief."), ChatMessage("user", "Hello")]
MODEL = "qwen/qwen3.5-9b"
GROQ_KEY = "gsk_test_placeholder_not_a_real_key"
LOCAL_SETTINGS = {
    "llm_provider": "lm_studio",
    "lm_studio_model": MODEL,
    "lm_studio_base_url": "http://127.0.0.1:1235/v1",
    "lm_studio_api_key": None,
    "lm_studio_enabled": False,
    "groq_api_key": None,  # no cloud key anywhere
}


def local_settings(**overrides: object):
    values = {**LOCAL_SETTINGS, **overrides}
    patches = [patch.object(settings, name, value) for name, value in values.items()]

    class Stack:
        def __enter__(self) -> None:
            for active in patches:
                active.start()

        def __exit__(self, *exc: object) -> None:
            for active in reversed(patches):
                active.stop()

    return Stack()


def status_error(cls: type, status: int) -> Exception:
    return cls("local server said: secret-detail", response=httpx.Response(status, request=REQUEST), body=None)


def completion(text: object, finish_reason: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish_reason)],
        model=MODEL,
        usage=SimpleNamespace(prompt_tokens=900, completion_tokens=40),
    )


def mocked_local(result: object = None, error: Exception | None = None) -> OpenAICompatibleLLMProvider:
    create = AsyncMock(return_value=result, side_effect=error)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return OpenAICompatibleLLMProvider(client=client, model=MODEL, temperature=0.0, max_tokens=64, rate_limit_max_wait_seconds=0.0)


def calls(provider: OpenAICompatibleLLMProvider) -> int:
    return provider._client.chat.completions.create.await_count


class LocalOnlyConfigurationTests(unittest.TestCase):
    def test_factory_builds_only_the_local_provider_without_any_cloud_key(self) -> None:
        with local_settings(lm_studio_timeout_seconds=75.0):
            built = create_llm_provider()
        self.assertIs(type(built), OpenAICompatibleLLMProvider)  # no fallback wrapper, no Groq provider
        self.assertNotIsInstance(built, FallbackLLMProvider)
        self.assertEqual(built.model, MODEL)
        self.assertEqual(str(built._client.base_url), "http://127.0.0.1:1235/v1/")
        self.assertEqual(built._client.max_retries, 0)  # no hidden retry loop
        self.assertEqual(built._client.timeout, 75.0)  # configurable
        self.assertEqual(built._client.api_key, "lm-studio")  # placeholder; the server needs no key
        self.assertNotIn("groq", str(built._client.base_url))

    def test_the_groq_key_is_never_used_or_sent_in_local_only_mode(self) -> None:
        with local_settings(groq_api_key=SecretStr(GROQ_KEY)):
            built = create_llm_provider()
        self.assertNotEqual(built._client.api_key, GROQ_KEY)
        self.assertEqual(str(built._client.base_url), "http://127.0.0.1:1235/v1/")

    def test_a_blank_model_is_a_configuration_error_not_a_guess(self) -> None:
        for model in ("", "   "):
            with self.subTest(model=model), local_settings(lm_studio_model=model):
                with self.assertRaises(LLMConfigurationError):
                    create_llm_provider()

    def test_startup_validation_for_the_local_provider(self) -> None:
        with self.assertRaisesRegex(ValueError, "LM_STUDIO_MODEL is required"):
            Settings(_env_file=None, llm_provider="lm_studio")
        with self.assertRaisesRegex(ValueError, "must point at this machine"):
            Settings(_env_file=None, llm_provider="lm_studio", lm_studio_model=MODEL, lm_studio_base_url="http://192.168.1.9:1235/v1")
        ok = Settings(_env_file=None, llm_provider="lm_studio", lm_studio_model=MODEL, lm_studio_base_url="http://127.0.0.1:1235/v1")
        self.assertFalse(ok.groq_api_key and ok.groq_api_key.get_secret_value())  # no cloud key needed (unset or empty)
        self.assertEqual(Settings(_env_file=None).llm_provider, "groq")  # default unchanged: rollback is one setting
        with self.assertRaises(ValueError):
            Settings(_env_file=None, llm_provider="unknown")

    def test_the_local_timeout_is_configurable_and_bounded(self) -> None:
        self.assertEqual(Settings(_env_file=None, lm_studio_timeout_seconds=300).lm_studio_timeout_seconds, 300)
        for bad in (0, -1, 601):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Settings(_env_file=None, lm_studio_timeout_seconds=bad)


class LocalProviderFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_local_generation_returns_only_the_final_text(self) -> None:
        local = mocked_local(completion("<think>reasoning</think>\nINR 1.5 crore [S1]."))
        response = await local.generate(MESSAGES)
        self.assertEqual((response.text, response.model), ("INR 1.5 crore [S1].", MODEL))
        self.assertEqual(calls(local), 1)

    async def test_unreachable_or_unavailable_server_is_one_attempt_and_a_safe_error(self) -> None:
        for label, error in (
            ("not running", openai.APIConnectionError(request=REQUEST)),
            ("503", status_error(openai.InternalServerError, 503)),
        ):
            with self.subTest(label), self.assertLogs("app.llm", "WARNING") as logs:
                local = mocked_local(error=error)
                with self.assertRaises(LLMProviderUnavailableError) as caught:
                    await local.generate(MESSAGES)
                self.assertEqual(calls(local), 1)
                self.assertNotIn("secret-detail", str(caught.exception) + "\n".join(logs.output))

    async def test_missing_or_wrong_model_is_a_provider_error_not_a_retry(self) -> None:
        for error in (status_error(openai.NotFoundError, 404), status_error(openai.BadRequestError, 400)):
            with self.subTest(error=type(error).__name__), self.assertLogs("app.llm", "WARNING") as logs:
                local = mocked_local(error=error)
                with self.assertRaises(LLMProviderError) as caught:
                    await local.generate(MESSAGES)
                self.assertNotIsInstance(caught.exception, (LLMProviderTimeoutError, LLMProviderUnavailableError))
                self.assertEqual(calls(local), 1)
                self.assertNotIn("secret-detail", str(caught.exception) + "\n".join(logs.output))

    async def test_local_timeout_is_a_timeout_error_after_one_attempt(self) -> None:
        local = mocked_local(error=openai.APITimeoutError(request=REQUEST))
        with self.assertLogs("app.llm", "WARNING"), self.assertRaises(LLMProviderTimeoutError):
            await local.generate(MESSAGES)
        self.assertEqual(calls(local), 1)

    async def test_invalid_empty_or_thinking_only_output_is_rejected(self) -> None:
        cases = {
            "no content": completion(None),
            "blank": completion("   "),
            "only thinking": completion("<think>never reached an answer</think>"),
            "unclosed thinking": completion("<think>still reasoning"),
            "ran out of tokens": completion("", finish_reason="length"),
            "malformed": SimpleNamespace(choices=[]),
        }
        for label, result in cases.items():
            with self.subTest(label):
                local = mocked_local(result)
                with self.assertRaises(LLMProviderError):
                    await local.generate(MESSAGES)
                self.assertEqual(calls(local), 1)


class LocalGenerationLayerTests(unittest.IsolatedAsyncioTestCase):
    async def test_citations_sources_and_authorization_context_are_preserved(self) -> None:
        user = make_user()
        context = await build_context(FINANCE_RESULTS, user)
        local = mocked_local(completion("INR 1.5 crore【S1】, reviewed quarterly [S2], invented [S9]."))

        result = await AnswerGenerator(local).generate(RagQuery(query=QUESTION), context, user=user)

        prompt = "\n".join(m["content"] for m in local._client.chat.completions.create.await_args.kwargs["messages"])
        for item in context.items:
            self.assertIn(item.content, prompt)
        for absent in ("HR salary bands L3 Senior Engineer", "CONFIDENTIAL HR", "Rahul Gupta"):
            self.assertNotIn(absent, prompt)
        self.assertEqual(result.status, "answered")
        self.assertEqual((result.unverified_source_numbers, result.rejected_source_numbers), ((1, 2), (9,)))
        self.assertEqual(result.citation_check, "partial")
        self.assertNotIn("[S9]", result.answer)
        self.assertIs(result.context, context)

    async def test_no_authorized_context_makes_no_model_call(self) -> None:
        user = make_user()
        context = await build_context([], user)
        local = mocked_local(completion("must not be used"))
        result = await AnswerGenerator(local).generate(RagQuery(query=QUESTION), context, user=user)
        self.assertEqual((result.status, result.provider_called, calls(local)), ("no_authorized_context", False, 0))

    async def test_a_context_built_for_someone_else_makes_no_model_call(self) -> None:
        context = await build_context(FINANCE_RESULTS, make_user())
        local = mocked_local(completion("must not be used"))
        with self.assertRaises(RagGenerationError) as caught:
            await AnswerGenerator(local).generate(RagQuery(query=QUESTION), context, user=make_user())
        self.assertEqual(caught.exception.category, "invalid_context")
        self.assertEqual(calls(local), 0)

    async def test_local_failures_map_to_the_existing_stable_categories(self) -> None:
        user = make_user()
        context = await build_context(FINANCE_RESULTS, user)
        cases = (
            (openai.APIConnectionError(request=REQUEST), "provider_error"),
            (status_error(openai.NotFoundError, 404), "provider_error"),
            (openai.APITimeoutError(request=REQUEST), "provider_timeout"),
        )
        for error, category in cases:
            with self.subTest(category=category, error=type(error).__name__), self.assertLogs("app", "WARNING"):
                generator = AnswerGenerator(mocked_local(error=error))
                with self.assertRaises(RagGenerationError) as caught:
                    await generator.generate(RagQuery(query=QUESTION), context, user=user)
                self.assertEqual(caught.exception.category, category)
                self.assertNotIn("secret-detail", str(caught.exception))


class LocalAssistantApiTests(DemoDatasetTestCase):
    """The real endpoint, real authorization and retrieval, real provider factory; only the HTTP client is mocked."""

    EMBED = True

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.local = mocked_local(completion("The Finance budget is INR 1.5 crore [S1]."))
        self.builders: list[RecordingContextBuilder] = []
        from demo_fixtures import lexical_service
        from app.services.vector_search import VectorSearchService

        def make_builder(session_factory):  # noqa: ANN001
            embeddings = lexical_service()
            search = VectorSearchService(
                session_factory, embedding_dimension=embeddings.dimension, embedding_model=embeddings.model
            )
            builder = RecordingContextBuilder(search, embeddings)
            self.builders.append(builder)
            return builder

        self.patches = [
            patch("app.api.v1.assistant.create_context_builder", side_effect=make_builder),
            patch("app.services.llm.provider.create_local_provider", side_effect=lambda: self.local),
            patch.object(settings, "llm_provider", "lm_studio"),
            patch.object(settings, "lm_studio_model", MODEL),
            patch.object(settings, "groq_api_key", None),
        ]
        for active in self.patches:
            active.start()

    async def asyncTearDown(self) -> None:
        for active in reversed(self.patches):
            active.stop()
        await super().asyncTearDown()

    async def ask(self, email: str, query: str = FINANCE_QUESTION) -> tuple[int, dict]:
        status, _, body = await self.request_json("POST", PATH, {"query": query}, self.token_headers(self.user_id(email)))
        return status, body

    async def test_local_only_answer_keeps_the_assistant_contract_without_a_cloud_key(self) -> None:
        status, body = await self.ask(FINANCE_MANAGER)
        self.assertEqual(status, 200, body)
        self.assertEqual(body["status"], "answered")
        self.assertEqual(body["answer"], "The Finance budget is INR 1.5 crore [S1].")
        self.assertEqual((body["unverified_source_numbers"], body["citation_check"]), ([1], "passed"))
        self.assertTrue(body["sources"])
        self.assertEqual(calls(self.local), 1)

    async def test_restricted_documents_never_reach_the_local_model(self) -> None:
        status, body = await self.ask(FINANCE_MANAGER, "HR salary bands promotion merit increase")
        self.assertEqual(status, 200, body)
        forbidden = self.document_id("HR_Policy.pdf")
        self.assertNotIn(str(forbidden), json.dumps(body))
        if calls(self.local):
            prompt = "\n".join(m["content"] for m in self.local._client.chat.completions.create.await_args.kwargs["messages"])
            async with self.session_factory() as session:
                for text in await session.scalars(select(models.DocumentChunk.content).where(models.DocumentChunk.document_id == forbidden)):
                    self.assertNotIn(text, prompt)

    async def test_an_account_without_read_permission_is_refused_before_any_model_call(self) -> None:
        from uuid import uuid4

        async with self.session_factory() as session:
            user = models.User(email=f"noread-{uuid4().hex}@example.invalid", full_name="No Read", is_active=True)
            session.add(user)
            await session.commit()
            user_id = user.id
        status, _, body = await self.request_json("POST", PATH, {"query": FINANCE_QUESTION}, self.token_headers(user_id))
        self.assertEqual(status, 403)
        self.assertEqual((self.builders, calls(self.local)), ([], 0))

    async def test_local_failures_return_the_existing_safe_errors(self) -> None:
        cases = (
            (openai.APIConnectionError(request=REQUEST), 502, "The language model request failed."),
            (status_error(openai.NotFoundError, 404), 502, "The language model request failed."),
            (openai.APITimeoutError(request=REQUEST), 504, "The language model did not respond in time."),
        )
        for error, expected_status, message in cases:
            with self.subTest(error=type(error).__name__):
                self.local = mocked_local(error=error)
                with self.assertLogs("app", "WARNING") as logs:
                    status, body = await self.ask(FINANCE_MANAGER)
                self.assertEqual((status, body["error"]["message"]), (expected_status, message))
                self.assertNotIn("answer", body)
                self.assertNotIn("secret-detail", json.dumps(body) + "\n".join(logs.output))
                self.assertNotIn(FINANCE_QUESTION, "\n".join(logs.output))
                self.assertEqual(calls(self.local), 1)

    async def test_empty_local_output_is_a_safe_error_never_an_invented_answer(self) -> None:
        for result in (completion("   "), completion("<think>no answer</think>"), completion("", finish_reason="length")):
            self.local = mocked_local(result)
            with self.assertLogs("app", "WARNING"):
                status, body = await self.ask(FINANCE_MANAGER)
            self.assertEqual(status, 502)
            self.assertNotIn("answer", body)

    async def test_a_missing_model_setting_fails_before_retrieval(self) -> None:
        self.patches[1].stop()  # the real create_local_provider
        try:
            with patch.object(settings, "lm_studio_model", ""), self.assertLogs("app", "WARNING"):
                status, body = await self.ask(FINANCE_MANAGER)
        finally:
            self.patches[1].start()
        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["message"], "The language model is not configured.")
        self.assertEqual(self.builders, [])


if __name__ == "__main__":
    unittest.main()
