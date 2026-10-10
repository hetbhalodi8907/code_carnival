"""Chat-completion provider for answer generation.

Groq and LM Studio both expose OpenAI-compatible APIs, so the ``openai`` SDK is used with a
different base URL for each. Only the final assistant text is returned: reasoning traces that
some models emit are dropped, and provider error text is never logged or surfaced
because it can echo request content.
"""

from __future__ import annotations

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import settings


logger = logging.getLogger("app.llm")

Role = Literal["system", "user", "assistant"]
_ROLES = frozenset({"system", "user", "assistant"})


class LLMProviderError(RuntimeError):
    """Raised when the LLM provider cannot produce a valid answer."""


class LLMProviderTimeoutError(LLMProviderError):
    """Raised when the provider does not answer within LLM_TIMEOUT_SECONDS."""


class LLMProviderRateLimitError(LLMProviderError):
    """Raised when the provider's rate limit is still in effect after one short wait."""


class LLMProviderUnavailableError(LLMProviderError):
    """Raised when the provider is unreachable or answers HTTP 503 (a transient condition)."""


class LLMConfigurationError(ValueError):
    """Raised when the LLM provider is not configured."""


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    provider: str | None = None
    """Identifier of the provider that produced this response ("groq", "lm_studio"); None if unknown."""


class LLMProvider(ABC):
    @property
    @abstractmethod
    def model(self) -> str:
        """Identifier of the model that generates answers."""

    @abstractmethod
    async def generate(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Return the assistant's final text for a validated message list."""


class OpenAICompatibleLLMProvider(LLMProvider):
    """Chat provider for any OpenAI-compatible endpoint (Groq or the local LM Studio server)."""

    def __init__(
        self,
        *,
        client: Any,
        model: str,
        temperature: float,
        max_tokens: int,
        rate_limit_max_wait_seconds: float | None = None,
        provider_name: str | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("LLM model must not be empty.")
        if max_tokens <= 0:
            raise ValueError("LLM max_tokens must be greater than zero.")
        # None means the configured default. A fallback setup passes 0 so a rate limit fails over at once.
        self._rate_limit_max_wait = (
            settings.llm_rate_limit_max_wait_seconds if rate_limit_max_wait_seconds is None else rate_limit_max_wait_seconds
        )
        self._client = client
        self._provider_name = provider_name
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        _validate_messages(messages)
        waited = False
        while True:
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": m.role, "content": m.content} for m in messages],
                    temperature=self._temperature if temperature is None else temperature,
                    max_tokens=self._max_tokens if max_tokens is None else max_tokens,
                )
                break
            except Exception as exc:
                logger.warning("LLM provider request failed error_type=%s", type(exc).__name__)
                if _is_timeout(exc):
                    raise LLMProviderTimeoutError("The language model request timed out.") from exc
                if _is_rate_limit(exc):
                    # Per-minute token limits clear in seconds: wait once if the provider says how long.
                    wait = _retry_after_seconds(exc)
                    if not waited and wait is not None and wait <= self._rate_limit_max_wait:
                        waited = True
                        logger.info("LLM rate limited; waiting %.1fs before one retry", wait)
                        await asyncio.sleep(wait)
                        continue
                    raise LLMProviderRateLimitError("The language model is rate limited.") from exc
                if _is_unavailable(exc):
                    raise LLMProviderUnavailableError("The language model is temporarily unavailable.") from exc
                raise LLMProviderError("The language model request failed.") from exc
        return _parse_response(response, self._model, self._provider_name)


def _is_timeout(exc: Exception) -> bool:
    from openai import APITimeoutError

    return isinstance(exc, (TimeoutError, APITimeoutError))


def _is_rate_limit(exc: Exception) -> bool:
    from openai import RateLimitError

    return isinstance(exc, RateLimitError)


def _is_unavailable(exc: Exception) -> bool:
    """Unreachable (connection failure) or HTTP 503. Auth, request and other errors are not transient."""
    from openai import APIConnectionError, APIStatusError

    return isinstance(exc, APIConnectionError) or (isinstance(exc, APIStatusError) and exc.status_code == 503)


def _retry_after_seconds(exc: Exception) -> float | None:
    """The provider's own wait hint (Retry-After header, in seconds), if it sent a usable one."""
    try:
        value = float(exc.response.headers["retry-after"])  # type: ignore[attr-defined]
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    return value if 0 <= value < float("inf") else None


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _validate_messages(messages: Sequence[ChatMessage]) -> None:
    if not messages:
        raise LLMProviderError("At least one message is required.")
    for message in messages:
        if message.role not in _ROLES:
            raise LLMProviderError("Message role is not supported.")
        if not isinstance(message.content, str) or not message.content.strip():
            raise LLMProviderError("Message content must be non-empty text.")


def _parse_response(response: Any, requested_model: str, provider_name: str | None = None) -> LLMResponse:
    try:
        choice = response.choices[0]
        content = choice.message.content
        finish_reason = getattr(choice, "finish_reason", None)
    except (AttributeError, IndexError, TypeError) as exc:
        raise LLMProviderError("The language model returned a malformed response.") from exc

    if isinstance(content, str):
        # Some local reasoning models (Qwen) put their thinking inline; it is never part of the answer.
        content = _THINK_BLOCK.sub("", content)
        if "<think>" in content:  # an unclosed block means the answer was never reached
            content = ""
    if not isinstance(content, str) or not content.strip():
        if finish_reason == "length":
            raise LLMProviderError("The language model ran out of output tokens before answering.")
        raise LLMProviderError("The language model returned an empty answer.")

    usage = getattr(response, "usage", None)
    return LLMResponse(
        text=content.strip(),
        model=getattr(response, "model", None) or requested_model,
        finish_reason=finish_reason,
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
        provider=provider_name,
    )


def validate_llm_configuration() -> str:
    """Return the API key, or raise if the configured provider cannot be used."""
    if settings.llm_provider != "groq":
        raise LLMConfigurationError(f"Unsupported LLM provider: {settings.llm_provider}.")
    api_key = settings.groq_api_key.get_secret_value() if settings.groq_api_key else ""
    if not api_key:
        raise LLMConfigurationError("GROQ_API_KEY is required for the Groq LLM provider.")
    return api_key


_FALLBACK_TRIGGERS = (LLMProviderRateLimitError, LLMProviderTimeoutError, LLMProviderUnavailableError)
# LM Studio ignores the key unless server authentication is on; the client library needs a non-empty value.
_LM_STUDIO_PLACEHOLDER_KEY = "lm-studio"


class FallbackLLMProvider(LLMProvider):
    """Primary provider with one optional local fallback attempt.

    The fallback runs only after the primary raised a rate limit, timeout or unavailability error.
    Request, authentication and validation errors are never retried elsewhere. It receives exactly
    the messages the primary received, which the generation layer built from authorized context
    only. If the fallback also fails, the PRIMARY error is raised, so the caller's existing safe
    behavior (429, 504, 502) is unchanged. Only error types and the model ID are logged.
    """

    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def model(self) -> str:
        return self._primary.model

    async def generate(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        try:
            return await self._primary.generate(messages, temperature=temperature, max_tokens=max_tokens)
        except _FALLBACK_TRIGGERS as primary_error:
            logger.warning("Primary LLM unavailable error_type=%s; trying the local fallback once", type(primary_error).__name__)
            try:
                # The primary's token budget is not meaningful for a different model; the fallback uses its own.
                response = await self._fallback.generate(messages, temperature=temperature)
            except Exception as fallback_error:  # noqa: BLE001 - any failure leaves the primary's error in force
                logger.warning("Local fallback failed error_type=%s", type(fallback_error).__name__)
                raise primary_error from None
            logger.warning("Answer generated by the local fallback model=%s", response.model)
            return response


def create_llm_provider() -> LLMProvider:
    """Create the configured provider (with the optional local fallback) without exposing keys."""
    if settings.llm_provider == "lm_studio":
        # Local-only: no Groq key is read or required, there is no fallback wrapper and no cloud call.
        return create_local_provider()
    api_key = validate_llm_configuration()

    from openai import AsyncOpenAI

    fallback_enabled = settings.lm_studio_enabled
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
        # With a fallback, fail over at once instead of waiting through the SDK's own retries.
        max_retries=0 if fallback_enabled else 2,
    )
    primary = OpenAICompatibleLLMProvider(
        client=client,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_output_tokens,
        rate_limit_max_wait_seconds=0.0 if fallback_enabled else None,
        provider_name="groq",
    )
    if not fallback_enabled:
        return primary
    return FallbackLLMProvider(primary, create_local_provider())


def create_local_provider() -> OpenAICompatibleLLMProvider:
    """The LM Studio provider (OpenAI-compatible), using the exact model ID from the settings."""
    from openai import AsyncOpenAI

    if not settings.lm_studio_model.strip():
        raise LLMConfigurationError("LM_STUDIO_MODEL is required for the local LLM provider.")

    key = settings.lm_studio_api_key.get_secret_value() if settings.lm_studio_api_key else ""
    client = AsyncOpenAI(
        api_key=key or _LM_STUDIO_PLACEHOLDER_KEY,
        base_url=settings.lm_studio_base_url,
        timeout=settings.lm_studio_timeout_seconds,
        max_retries=0,
    )
    return OpenAICompatibleLLMProvider(
        client=client,
        model=settings.lm_studio_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.lm_studio_max_output_tokens,
        rate_limit_max_wait_seconds=0.0,
        provider_name="lm_studio",
    )
