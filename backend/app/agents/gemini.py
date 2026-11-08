"""Google Gemini runtime for the research agents (free tier via a Google AI Studio key).

Same contract as the Claude runtime: the agents send a system prompt, an evidence
payload and a JSON schema; this returns the parsed JSON. The agents have no tools,
and every output still goes through the deterministic verifier.

The Gemini API's free tier is rate-limited, and Google's terms for unpaid usage
allow prompts to be used to improve its products. Only public market data and
provider text are sent here; no personal data.
"""

from __future__ import annotations

import json
import time
from typing import Callable

from .llm import LLMError, LLMUnavailable


PER_REQUEST_TIMEOUT_S = 45  # an overloaded model can hang; move on instead of using the whole agent budget


class GeminiLLM:
    def __init__(self, model: str, timeout: float, api_key: str | None, client=None,
                 sleep: Callable[[float], None] = time.sleep, retries: int = 2,
                 fallbacks: list[str] | None = None) -> None:
        if not api_key and client is None:
            raise LLMUnavailable("No Gemini API key configured (set GEMINI_API_KEY in .env; free key at aistudio.google.com/apikey).")
        self.model = model
        # Free-tier models are sometimes overloaded (503 / 504); try the next one instead of failing.
        self.models = list(dict.fromkeys([model] + [m for m in (fallbacks or []) if m]))
        self.sleep = sleep
        self.retries = retries
        if client is None:
            from google import genai
            from google.genai import types

            per_request = min(timeout, PER_REQUEST_TIMEOUT_S)
            client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(per_request * 1000)))
        self.client = client

    def generate(self, *, system: str, user: str, schema: dict, max_tokens: int) -> dict:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            max_output_tokens=max_tokens,
            temperature=0.2,
        )
        response, used, problems = None, None, []
        for model in self.models:
            for attempt in range(self.retries + 1):
                try:
                    response = self.client.models.generate_content(model=model, contents=user, config=config)
                    used = model
                    break
                except errors.ClientError as exc:
                    msg = exc.message or str(exc)
                    if exc.code in (401, 403) or (exc.code == 400 and "api key" in msg.lower()):
                        raise LLMUnavailable(f"Gemini rejected the API key: {msg}") from exc
                    if exc.code == 404:
                        problems.append(f"{model}: not available")
                        break  # try the next model
                    if exc.code == 429:
                        if attempt < self.retries:
                            self.sleep(5 * 2 ** attempt)
                            continue
                        problems.append(f"{model}: free-tier rate limit")
                        break
                    raise LLMError(f"Gemini API error {exc.code}: {msg}") from exc
                except errors.ServerError as exc:
                    problems.append(f"{model}: {exc.code} {exc.status or 'server error'}")
                    break  # overloaded or timed out: move to the next model
                except errors.APIError as exc:
                    raise LLMError(f"Gemini API error {exc.code}: {exc.message}") from exc
                except Exception as exc:  # client-side timeout or connection failure
                    problems.append(f"{model}: {type(exc).__name__}")
                    break
            if response is not None:
                break
        if response is None:
            raise LLMError("No Gemini model answered (" + "; ".join(problems) + "). Try again in a minute.")

        candidates = getattr(response, "candidates", None) or []
        finish = str(getattr(candidates[0], "finish_reason", "") or "") if candidates else ""
        if "MAX_TOKENS" in finish:
            raise LLMError("Gemini output was truncated at the token limit.")
        if any(block in finish for block in ("SAFETY", "BLOCKLIST", "PROHIBITED", "RECITATION")):
            raise LLMError(f"Gemini declined the request ({finish}).")
        text = getattr(response, "text", None)
        if not text:
            raise LLMError("Gemini returned no text.")
        try:
            output = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Gemini returned invalid JSON: {exc}") from exc
        usage = getattr(response, "usage_metadata", None)
        return {
            "output": output,
            "model": getattr(response, "model_version", None) or used,
            "usage": {"input_tokens": getattr(usage, "prompt_token_count", None) or 0,
                      "output_tokens": getattr(usage, "candidates_token_count", None) or 0},
            "request_id": getattr(response, "response_id", None),
        }
