"""LLM runtime behind an internal interface (plan section 12.1).

Agents only see `StructuredLLM.generate`, so the provider can change without
touching agent logic. The Claude implementation uses structured outputs
(`output_config.format`) and has no tools at all: agents cannot fetch URLs,
place orders or call anything (plan section 14, strict tool allowlists).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol

import anthropic


class LLMUnavailable(Exception):
    """No usable credentials or the runtime is disabled. The agent is skipped, not failed."""


class LLMError(Exception):
    """The call was attempted and failed (network, rate limit, refusal, truncation)."""


class StructuredLLM(Protocol):
    model: str

    def generate(self, *, system: str, user: str, schema: dict, max_tokens: int) -> dict:
        """Return {"output": <dict matching schema>, "model": str, "usage": dict, "request_id": str | None}."""


def agent_runtime(settings) -> dict:
    """Which LLM provider the agents use, its model, and whether credentials exist."""
    choice = (getattr(settings, "agent_provider", "auto") or "auto").lower()
    has_claude = credentials_available(settings.anthropic_api_key)
    has_gemini = bool(getattr(settings, "gemini_api_key", None))
    if choice == "auto":
        choice = "anthropic" if has_claude else "gemini" if has_gemini else "anthropic"
    if choice == "gemini":
        return {"provider": "gemini", "model": settings.gemini_model, "credentials": has_gemini}
    return {"provider": "anthropic", "model": settings.agent_model, "credentials": has_claude}


def make_llm(settings, alternate: bool = False) -> StructuredLLM:
    """`alternate=True` gives opposing debate roles a different model where one is available."""
    rt = agent_runtime(settings)
    if rt["provider"] == "gemini":
        from .gemini import GeminiLLM

        fallbacks = [m.strip() for m in (getattr(settings, "gemini_fallback_models", "") or "").split(",") if m.strip()]
        model = settings.gemini_model
        if alternate:
            others = [m for m in fallbacks if m != model]
            if others:
                model, fallbacks = others[0], others[1:] + [settings.gemini_model]
        return GeminiLLM(model, settings.agent_timeout_seconds, settings.gemini_api_key, fallbacks=fallbacks)
    return ClaudeLLM(settings.agent_model, settings.agent_effort, settings.agent_timeout_seconds, settings.anthropic_api_key)


def credentials_available(api_key: str | None) -> bool:
    if api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    return (Path.home() / ".config" / "anthropic").exists()  # `ant auth login` profile


class ClaudeLLM:
    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self, model: str, effort: str, timeout: float, api_key: str | None = None) -> None:
        if not credentials_available(api_key):
            raise LLMUnavailable("No Anthropic credentials configured (set ANTHROPIC_API_KEY in .env).")
        self.model = model
        self.effort = effort
        kwargs = {"timeout": timeout, "max_retries": 2}
        if api_key:
            kwargs["api_key"] = api_key
        self.client = anthropic.Anthropic(**kwargs)

    def generate(self, *, system: str, user: str, schema: dict, max_tokens: int) -> dict:
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
                # On a safety-classifier decline, the API retries on Anthropic's recommended fallback model.
                betas=[self.FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as exc:
            raise LLMUnavailable(f"Anthropic credentials were rejected: {exc.message}") from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMUnavailable(f"Anthropic API key lacks permission: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Anthropic rate limit reached; retry later.") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"Could not reach the Anthropic API: {exc}") from exc

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None) if response.stop_details else None
            raise LLMError(f"Model declined the request (category: {category}).")
        if response.stop_reason == "max_tokens":
            raise LLMError("Model output was truncated at max_tokens.")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LLMError("Model returned no text block.")
        try:
            output = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model returned invalid JSON: {exc}") from exc
        usage = response.usage
        return {
            "output": output,
            "model": response.model,
            "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
            "request_id": getattr(response, "_request_id", None),
        }
