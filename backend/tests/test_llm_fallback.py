"""Optional LM Studio fallback: mocked clients only (no Groq, no LM Studio, no network)."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import httpx
import openai
from pydantic import SecretStr

from app.core.config import Settings, settings
from app.schemas.rag import RagQuery
from app.services.llm.provider import (
    ChatMessage,
    FallbackLLMProvider,
    LLMProviderError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
    LLMProviderUnavailableError,
    OpenAICompatibleLLMProvider,
    create_llm_provider,
)
from app.services.rag.generation import AnswerGenerator
from test_rag_generation import FINANCE_RESULTS, QUESTION, build_context, make_user


REQUEST = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
MESSAGES = [ChatMessage("system", "Be brief."), ChatMessage("user", "Hello")]
GROQ_KEY = "gsk_test_placeholder_not_a_real_key"
LOCAL_MODEL = "qwen/qwen3.5-9b"


def status_error(cls: type, status: int, headers: dict | None = None) -> Exception:
    return cls("provider said: secret-detail", response=httpx.Response(status, headers=headers or {}, request=REQUEST), body=None)


def completion(text: object, model: str = "served-model") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason="stop")],
        model=model,
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3),
    )


def provider(name: str, *, result: object = None, error: Exception | None = None) -> OpenAICompatibleLLMProvider:
    create = AsyncMock(return_value=result, side_effect=error)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return OpenAICompatibleLLMProvider(client=client, model=name, temperature=0.0, max_tokens=64, rate_limit_max_wait_seconds=0.0)


def calls(p: OpenAICompatibleLLMProvider) -> int:
    return p._client.chat.completions.create.await_count


RATE_LIMIT = lambda: status_error(openai.RateLimitError, 429, {"retry-after": "600"})  # noqa: E731
TIMEOUT = lambda: openai.APITimeoutError(request=REQUEST)  # noqa: E731
UNAVAILABLE_503 = lambda: status_error(openai.InternalServerError, 503)  # noqa: E731
CONNECTION = lambda: openai.APIConnectionError(request=REQUEST)  # noqa: E731


class FallbackBehaviorTests(unittest.IsolatedAsyncioTestCase):
    def pair(self, primary_error=None, primary_result=None, local_error=None, local_result=None):
        primary = provider("groq-model", result=primary_result or completion("Groq answer"), error=primary_error)
        local = provider(LOCAL_MODEL, result=local_result or completion("Local answer", LOCAL_MODEL), error=local_error)
        return FallbackLLMProvider(primary, local), primary, local

    async def test_success_never_touches_the_local_model(self) -> None:
        wrapper, primary, local = self.pair()
        self.assertEqual((await wrapper.generate(MESSAGES)).text, "Groq answer")
        self.assertEqual((calls(primary), calls(local)), (1, 0))
        self.assertEqual(wrapper.model, "groq-model")

    async def test_rate_limit_triggers_exactly_one_local_attempt_without_waiting(self) -> None:
        wrapper, primary, local = self.pair(primary_error=RATE_LIMIT())
        with patch("app.services.llm.provider.asyncio.sleep") as sleep, self.assertLogs("app.llm", "WARNING") as logs:
            response = await wrapper.generate(MESSAGES)
        self.assertEqual((response.text, response.model), ("Local answer", LOCAL_MODEL))
        self.assertEqual((calls(primary), calls(local)), (1, 1))
        sleep.assert_not_awaited()
        self.assertIn(f"model={LOCAL_MODEL}", "\n".join(logs.output))

    async def test_transient_failures_trigger_the_fallback(self) -> None:
        for label, make in (("timeout", TIMEOUT), ("503", UNAVAILABLE_503), ("connection failure", CONNECTION)):
            with self.subTest(label), self.assertLogs("app.llm", "WARNING"):
                wrapper, primary, local = self.pair(primary_error=make())
                self.assertEqual((await wrapper.generate(MESSAGES)).text, "Local answer")
                self.assertEqual((calls(primary), calls(local)), (1, 1))

    async def test_non_transient_failures_never_trigger_the_fallback(self) -> None:
        cases = (
            ("authentication 401", status_error(openai.AuthenticationError, 401)),
            ("permission 403", status_error(openai.PermissionDeniedError, 403)),
            ("bad request 400", status_error(openai.BadRequestError, 400)),
            ("not found 404", status_error(openai.NotFoundError, 404)),
            ("unprocessable 422", status_error(openai.UnprocessableEntityError, 422)),
            ("server error 500", status_error(openai.InternalServerError, 500)),
        )
        for label, error in cases:
            with self.subTest(label), self.assertLogs("app.llm", "WARNING"):
                wrapper, primary, local = self.pair(primary_error=error)
                with self.assertRaises(LLMProviderError) as caught:
                    await wrapper.generate(MESSAGES)
                self.assertNotIsInstance(caught.exception, (LLMProviderRateLimitError, LLMProviderTimeoutError, LLMProviderUnavailableError))
                self.assertEqual((calls(primary), calls(local)), (1, 0))

    async def test_input_validation_failures_never_trigger_the_fallback(self) -> None:
        wrapper, primary, local = self.pair()
        for bad in ([], [ChatMessage("user", "  ")]):
            with self.assertRaises(LLMProviderError):
                await wrapper.generate(bad)
        self.assertEqual((calls(primary), calls(local)), (0, 0))

    async def test_a_failed_fallback_leaves_the_primary_error_and_one_attempt(self) -> None:
        cases = (
            ("local server not running", dict(local_error=CONNECTION())),
            ("model not loaded (404)", dict(local_error=status_error(openai.NotFoundError, 404))),
            ("local timeout", dict(local_error=TIMEOUT())),
            ("empty local answer", dict(local_result=completion("   "))),
            ("only inline thinking", dict(local_result=completion("<think>still reasoning"))),
        )
        for label, kwargs in cases:
            with self.subTest(label), self.assertLogs("app.llm", "WARNING") as logs:
                wrapper, primary, local = self.pair(primary_error=RATE_LIMIT(), **kwargs)
                with self.assertRaises(LLMProviderRateLimitError) as caught:  # the primary's error, as before
                    await wrapper.generate(MESSAGES)
                self.assertEqual((calls(primary), calls(local)), (1, 1))  # one attempt, no retry loop
                self.assertNotIn("secret-detail", str(caught.exception) + "\n".join(logs.output))
                self.assertIsNone(caught.exception.__cause__ and caught.exception.__cause__.__cause__)

    async def test_inline_thinking_is_removed_from_local_answers(self) -> None:
        wrapper, _, _ = self.pair(primary_error=TIMEOUT(), local_result=completion("<think>chain of thought</think>\nThe answer [S1]."))
        with self.assertLogs("app.llm", "WARNING"):
            self.assertEqual((await wrapper.generate(MESSAGES)).text, "The answer [S1].")


class FallbackSecurityAndCitationTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_local_model_gets_only_the_authorized_context_and_citations_are_validated(self) -> None:
        user = make_user()
        context = await build_context(FINANCE_RESULTS, user)
        primary = provider("groq-model", error=RATE_LIMIT())
        local = provider(LOCAL_MODEL, result=completion("INR 1.5 crore【S1】, reviewed quarterly [S2], invented [S9].", LOCAL_MODEL))
        generator = AnswerGenerator(FallbackLLMProvider(primary, local))

        with self.assertLogs("app.llm", "WARNING"):
            result = await generator.generate(RagQuery(query=QUESTION), context, user=user)

        sent_to_groq = primary._client.chat.completions.create.await_args.kwargs["messages"]
        sent_to_local = local._client.chat.completions.create.await_args.kwargs["messages"]
        self.assertEqual(sent_to_local, sent_to_groq)  # exactly what the generation layer built
        self.assertEqual([m["role"] for m in sent_to_local], ["system", "user"])
        prompt = "\n".join(m["content"] for m in sent_to_local)
        for item in context.items:
            self.assertIn(item.content, prompt)
        # Nothing but the authorized chunks: an unretrieved passage and a whole-database dump are absent.
        for absent in ("HR salary bands L3 Senior Engineer", "CONFIDENTIAL HR", "Rahul Gupta", "SELECT "):
            self.assertNotIn(absent, prompt)

        # Existing citation validation and source metadata are intact for a locally generated answer.
        self.assertEqual(result.status, "answered")
        self.assertEqual((result.unverified_source_numbers, result.rejected_source_numbers), ((1, 2), (9,)))
        self.assertEqual(result.citation_check, "partial")
        self.assertNotIn("[S9]", result.answer)
        self.assertEqual(result.model, LOCAL_MODEL)
        self.assertIs(result.context, context)
        self.assertEqual([item.chunk_id for item in result.context.items], [r.chunk_id for r in FINANCE_RESULTS])

    async def test_empty_context_still_makes_no_call_to_either_model(self) -> None:
        user = make_user()
        context = await build_context([], user)
        primary, local = provider("groq-model", error=RATE_LIMIT()), provider(LOCAL_MODEL)
        result = await AnswerGenerator(FallbackLLMProvider(primary, local)).generate(RagQuery(query=QUESTION), context, user=user)
        self.assertEqual((result.status, result.provider_called, calls(primary), calls(local)), ("no_authorized_context", False, 0, 0))

    async def test_when_both_fail_the_user_gets_the_existing_safe_error(self) -> None:
        from app.services.rag.generation import RagGenerationError

        user = make_user()
        context = await build_context(FINANCE_RESULTS, user)
        generator = AnswerGenerator(FallbackLLMProvider(provider("groq", error=RATE_LIMIT()), provider(LOCAL_MODEL, error=CONNECTION())))
        with self.assertLogs("app", "WARNING"), self.assertRaises(RagGenerationError) as caught:
            await generator.generate(RagQuery(query=QUESTION), context, user=user)
        self.assertEqual(caught.exception.category, "provider_rate_limited")
        self.assertNotIn("secret-detail", str(caught.exception))


class FallbackConfigurationTests(unittest.TestCase):
    def test_disabled_by_default_keeps_the_existing_provider_and_retries(self) -> None:
        with patch.object(settings, "groq_api_key", SecretStr(GROQ_KEY)), patch.object(settings, "lm_studio_enabled", False):
            built = create_llm_provider()
        self.assertIsInstance(built, OpenAICompatibleLLMProvider)
        self.assertEqual(built._client.max_retries, 2)
        self.assertEqual(built._rate_limit_max_wait, settings.llm_rate_limit_max_wait_seconds)
        self.assertFalse(Settings(_env_file=None).lm_studio_enabled)

    def test_enabled_builds_a_fallback_on_this_machine_with_fast_failover(self) -> None:
        with (
            patch.object(settings, "groq_api_key", SecretStr(GROQ_KEY)),
            patch.object(settings, "lm_studio_enabled", True),
            patch.object(settings, "lm_studio_model", LOCAL_MODEL),
            patch.object(settings, "lm_studio_base_url", "http://127.0.0.1:1235/v1"),
            patch.object(settings, "lm_studio_api_key", None),
        ):
            built = create_llm_provider()
        self.assertIsInstance(built, FallbackLLMProvider)
        primary, local = built._primary, built._fallback
        self.assertEqual((primary.model, local.model), (settings.llm_model, LOCAL_MODEL))
        self.assertEqual((primary._client.max_retries, primary._rate_limit_max_wait), (0, 0.0))  # fail over at once
        self.assertEqual(str(local._client.base_url), "http://127.0.0.1:1235/v1/")
        self.assertEqual(local._client.api_key, "lm-studio")  # placeholder: no real key needed when auth is off
        self.assertNotEqual(local._client.api_key, GROQ_KEY)  # the Groq key is never sent to the local server

    def test_a_configured_local_key_is_used_without_appearing_in_repr(self) -> None:
        configured = Settings(_env_file=None, lm_studio_enabled=True, lm_studio_model=LOCAL_MODEL, lm_studio_api_key=SecretStr("local-secret-value"))
        self.assertNotIn("local-secret-value", repr(configured))
        with (
            patch.object(settings, "groq_api_key", SecretStr(GROQ_KEY)),
            patch.object(settings, "lm_studio_enabled", True),
            patch.object(settings, "lm_studio_model", LOCAL_MODEL),
            patch.object(settings, "lm_studio_api_key", SecretStr("local-secret-value")),
        ):
            built = create_llm_provider()
        self.assertEqual(built._fallback._client.api_key, "local-secret-value")

    def test_unsafe_or_incomplete_settings_are_rejected_at_startup(self) -> None:
        with self.assertRaisesRegex(ValueError, "LM_STUDIO_MODEL is required"):
            Settings(_env_file=None, lm_studio_enabled=True)
        for url in ("http://192.168.1.20:1234/v1", "https://api.example.com/v1", "http://lmstudio.example/v1"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "must point at this machine"):
                Settings(_env_file=None, lm_studio_enabled=True, lm_studio_model=LOCAL_MODEL, lm_studio_base_url=url)
        for url in ("http://localhost:1234/v1", "http://127.0.0.1:1235/v1", "http://[::1]:1234/v1"):
            Settings(_env_file=None, lm_studio_enabled=True, lm_studio_model=LOCAL_MODEL, lm_studio_base_url=url)
        # Disabled: the other values are not validated, so a leftover URL never blocks startup.
        Settings(_env_file=None, lm_studio_enabled=False, lm_studio_base_url="http://192.168.1.20:1234/v1")

    def test_import_surface(self) -> None:
        from app.services.llm import FallbackLLMProvider as exported

        self.assertIs(exported, FallbackLLMProvider)


if __name__ == "__main__":
    unittest.main()
