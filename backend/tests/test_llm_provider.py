import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import openai
from pydantic import SecretStr

from app.core.config import Settings, settings
from app.services.llm.provider import (
    ChatMessage,
    LLMConfigurationError,
    LLMProviderError,
    LLMProviderRateLimitError,
    LLMProviderTimeoutError,
    OpenAICompatibleLLMProvider,
    create_llm_provider,
)


FAKE_KEY = "gsk_test_placeholder_not_a_real_key"


def completion(content: object, *, finish_reason: str = "stop", reasoning: str | None = None) -> SimpleNamespace:
    message = SimpleNamespace(content=content, reasoning=reasoning)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        model="served-model",
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
    )


def provider_with(response: object = None, *, error: Exception | None = None) -> OpenAICompatibleLLMProvider:
    create = AsyncMock(return_value=response, side_effect=error)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return OpenAICompatibleLLMProvider(client=client, model="test-model", temperature=0.0, max_tokens=256)


MESSAGES = [ChatMessage("system", "Be brief."), ChatMessage("user", "Hello")]


class LLMConfigurationTests(unittest.TestCase):
    def test_defaults_target_groq_without_a_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            configured = Settings(_env_file=None)

        self.assertEqual(configured.llm_provider, "groq")
        self.assertEqual(configured.llm_model, "openai/gpt-oss-120b")
        self.assertEqual(configured.llm_base_url, "https://api.groq.com/openai/v1")
        self.assertIsNone(configured.groq_api_key)
        self.assertEqual(configured.llm_temperature, 0.0)

    def test_environment_overrides_and_validation(self) -> None:
        environment = {"GROQ_API_KEY": FAKE_KEY, "LLM_MODEL": "openai/gpt-oss-20b", "LLM_MAX_OUTPUT_TOKENS": "512"}
        with patch.dict(os.environ, environment, clear=True):
            configured = Settings(_env_file=None)
            with self.assertRaises(ValueError):
                Settings(_env_file=None, llm_temperature=3.0)
            with self.assertRaises(ValueError):
                Settings(_env_file=None, llm_provider="unknown")

        self.assertEqual(configured.llm_model, "openai/gpt-oss-20b")
        self.assertEqual(configured.llm_max_output_tokens, 512)
        self.assertEqual(configured.groq_api_key.get_secret_value(), FAKE_KEY)
        self.assertNotIn(FAKE_KEY, repr(configured))

    def test_missing_or_empty_key_is_a_configuration_error(self) -> None:
        for key in (None, SecretStr("")):
            with patch.object(settings, "groq_api_key", key):
                with self.assertRaisesRegex(LLMConfigurationError, "GROQ_API_KEY"):
                    create_llm_provider()

    def test_factory_builds_provider_without_network(self) -> None:
        with patch.object(settings, "groq_api_key", SecretStr(FAKE_KEY)):
            provider = create_llm_provider()

        self.assertEqual(provider.model, settings.llm_model)


class OpenAICompatibleLLMProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_returns_only_final_text(self) -> None:
        provider = provider_with(completion("  Hi there.  ", reasoning="internal chain of thought"))

        response = await provider.generate(MESSAGES)

        self.assertEqual(response.text, "Hi there.")
        self.assertEqual(response.model, "served-model")
        self.assertEqual((response.prompt_tokens, response.completion_tokens), (11, 7))
        self.assertNotIn("chain of thought", repr(response))
        provider._client.chat.completions.create.assert_awaited_once_with(
            model="test-model",
            messages=[{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hello"}],
            temperature=0.0,
            max_tokens=256,
        )

    async def test_overrides_are_passed_through(self) -> None:
        provider = provider_with(completion("ok"))

        await provider.generate(MESSAGES, temperature=0.5, max_tokens=32)

        kwargs = provider._client.chat.completions.create.await_args.kwargs
        self.assertEqual((kwargs["temperature"], kwargs["max_tokens"]), (0.5, 32))

    async def test_invalid_messages_are_rejected_before_calling_provider(self) -> None:
        provider = provider_with(completion("unused"))
        for messages in ([], [ChatMessage("user", "  ")], [ChatMessage("tool", "x")]):  # type: ignore[arg-type]
            with self.assertRaises(LLMProviderError):
                await provider.generate(messages)
        provider._client.chat.completions.create.assert_not_awaited()

    async def test_provider_failure_is_wrapped_without_leaking_details(self) -> None:
        provider = provider_with(error=RuntimeError(f"401 invalid key {FAKE_KEY}"))

        with self.assertLogs("app.llm", level="WARNING") as captured:
            with self.assertRaises(LLMProviderError) as context:
                await provider.generate(MESSAGES)

        self.assertNotIn(FAKE_KEY, str(context.exception))
        self.assertNotIn(FAKE_KEY, "\n".join(captured.output))
        self.assertIn("RuntimeError", "\n".join(captured.output))

    async def test_timeouts_are_a_distinct_but_compatible_provider_error(self) -> None:
        timeout = openai.APITimeoutError(request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat"))
        for error in (timeout, TimeoutError()):
            with self.subTest(error=type(error).__name__), self.assertLogs("app.llm", level="WARNING"):
                with self.assertRaises(LLMProviderTimeoutError) as context:
                    await provider_with(error=error).generate(MESSAGES)
            self.assertIsInstance(context.exception, LLMProviderError)  # existing handlers still catch it
        with self.assertLogs("app.llm", level="WARNING"), self.assertRaises(LLMProviderError) as context:
            await provider_with(error=RuntimeError("connection reset")).generate(MESSAGES)
        self.assertNotIsInstance(context.exception, LLMProviderTimeoutError)

    async def test_a_short_rate_limit_is_waited_out_once_then_succeeds(self) -> None:
        def limited(retry_after: str | None) -> openai.RateLimitError:
            headers = {} if retry_after is None else {"retry-after": retry_after}
            response = httpx.Response(429, headers=headers, request=httpx.Request("POST", "https://api.groq.com/x"))
            return openai.RateLimitError("rate limited: org_secret_id", response=response, body=None)

        provider = provider_with(completion("Recovered."))
        provider._client.chat.completions.create.side_effect = [limited("2"), completion("Recovered.")]
        with patch("app.services.llm.provider.asyncio.sleep") as sleep, self.assertLogs("app.llm", level="INFO"):
            response = await provider.generate(MESSAGES)
        self.assertEqual(response.text, "Recovered.")
        sleep.assert_awaited_once_with(2.0)
        self.assertEqual(provider._client.chat.completions.create.await_count, 2)

        # Still limited after the one wait: a distinct, compatible error, with no provider text.
        provider = provider_with(completion("unused"))
        provider._client.chat.completions.create.side_effect = [limited("1"), limited("1"), limited("1")]
        with patch("app.services.llm.provider.asyncio.sleep"), self.assertLogs("app.llm", level="INFO") as captured:
            with self.assertRaises(LLMProviderRateLimitError) as context:
                await provider.generate(MESSAGES)
        self.assertIsInstance(context.exception, LLMProviderError)
        self.assertNotIn("org_secret_id", str(context.exception) + "\n".join(captured.output))
        self.assertEqual(provider._client.chat.completions.create.await_count, 2)  # one wait, one retry

        # A wait hint that is too long, or missing, fails immediately instead of hanging the request.
        for retry_after in ("600", None, "not-a-number"):
            provider = provider_with(completion("unused"))
            provider._client.chat.completions.create.side_effect = limited(retry_after)
            with patch("app.services.llm.provider.asyncio.sleep") as sleep, self.assertLogs("app.llm", level="INFO"):
                with self.assertRaises(LLMProviderRateLimitError):
                    await provider.generate(MESSAGES)
            sleep.assert_not_awaited()
            self.assertEqual(provider._client.chat.completions.create.await_count, 1)

    async def test_malformed_empty_and_truncated_responses_are_rejected(self) -> None:
        cases = {
            "no choices": SimpleNamespace(choices=[]),
            "no message": SimpleNamespace(choices=[SimpleNamespace()]),
            "null content": completion(None),
            "blank content": completion("   "),
            "non-text content": completion(["x"]),
        }
        for label, response in cases.items():
            with self.subTest(label):
                with self.assertRaises(LLMProviderError):
                    await provider_with(response).generate(MESSAGES)
        with self.assertRaisesRegex(LLMProviderError, "output tokens"):
            await provider_with(completion("", finish_reason="length")).generate(MESSAGES)

    def test_constructor_validation(self) -> None:
        with self.assertRaises(ValueError):
            OpenAICompatibleLLMProvider(client=None, model=" ", temperature=0.0, max_tokens=10)
        with self.assertRaises(ValueError):
            OpenAICompatibleLLMProvider(client=None, model="m", temperature=0.0, max_tokens=0)


if __name__ == "__main__":
    unittest.main()
