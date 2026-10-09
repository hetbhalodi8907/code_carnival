"""Chat-completion provider for answer generation.

Groq exposes an OpenAI-compatible API, so the existing ``openai`` SDK is used with a
different base URL. Only the final assistant text is returned: reasoning traces that
some models emit are dropped, and provider error text is never logged or surfaced
because it can echo request content.
"""

from __future__ import annotations

import logging
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
    """Chat provider for any OpenAI-compatible endpoint (configured for Groq)."""

    def __init__(self, *, client: Any, model: str, temperature: float, max_tokens: int) -> None:
        if not model.strip():
            raise ValueError("LLM model must not be empty.")
        if max_tokens <= 0:
            raise ValueError("LLM max_tokens must be greater than zero.")
        self._client = client
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
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=self._temperature if temperature is None else temperature,
                max_tokens=self._max_tokens if max_tokens is None else max_tokens,
            )
        except Exception as exc:
            logger.warning("LLM provider request failed error_type=%s", type(exc).__name__)
            raise LLMProviderError("The language model request failed.") from exc
        return _parse_response(response, self._model)


def _validate_messages(messages: Sequence[ChatMessage]) -> None:
    if not messages:
        raise LLMProviderError("At least one message is required.")
    for message in messages:
        if message.role not in _ROLES:
            raise LLMProviderError("Message role is not supported.")
        if not isinstance(message.content, str) or not message.content.strip():
            raise LLMProviderError("Message content must be non-empty text.")


def _parse_response(response: Any, requested_model: str) -> LLMResponse:
    try:
        choice = response.choices[0]
        content = choice.message.content
        finish_reason = getattr(choice, "finish_reason", None)
    except (AttributeError, IndexError, TypeError) as exc:
        raise LLMProviderError("The language model returned a malformed response.") from exc

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
    )


def validate_llm_configuration() -> str:
    """Return the API key, or raise if the configured provider cannot be used."""
    if settings.llm_provider != "groq":
        raise LLMConfigurationError(f"Unsupported LLM provider: {settings.llm_provider}.")
    api_key = settings.groq_api_key.get_secret_value() if settings.groq_api_key else ""
    if not api_key:
        raise LLMConfigurationError("GROQ_API_KEY is required for the Groq LLM provider.")
    return api_key


def create_llm_provider() -> OpenAICompatibleLLMProvider:
    """Create the configured provider without exposing the API key."""
    api_key = validate_llm_configuration()

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=2,
    )
    return OpenAICompatibleLLMProvider(
        client=client,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_output_tokens,
    )
