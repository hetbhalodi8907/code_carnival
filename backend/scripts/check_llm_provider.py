"""Live connectivity check for the configured LLM provider (makes one small API call).

Run from the backend directory:

    .venv/bin/python scripts/check_llm_provider.py

Reads the LLM settings from the environment or backend/.env: GROQ_API_KEY for Groq, or
LM_STUDIO_BASE_URL / LM_STUDIO_MODEL when LLM_PROVIDER=lm_studio. Keys are never printed.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

from app.services.llm.provider import (  # noqa: E402
    ChatMessage,
    LLMConfigurationError,
    LLMProviderError,
    create_llm_provider,
)


async def run() -> int:
    try:
        provider = create_llm_provider()
        started = time.perf_counter()
        response = await provider.generate(
            [
                ChatMessage("system", "You are a connectivity check. Reply with exactly: OK"),
                ChatMessage("user", "Connectivity check."),
            ],
            max_tokens=200,
        )
    except (LLMConfigurationError, LLMProviderError) as exc:
        print(f"LLM check FAILED: {exc}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started
    print(
        f"LLM check passed: model={response.model} latency={elapsed:.2f}s "
        f"finish_reason={response.finish_reason} prompt_tokens={response.prompt_tokens} "
        f"completion_tokens={response.completion_tokens} reply={response.text!r}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
