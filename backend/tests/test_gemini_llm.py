"""Gemini runtime: response parsing, retries, error mapping and provider selection (no network)."""

from types import SimpleNamespace

import pytest
from google.genai import errors

from app.agents.gemini import GeminiLLM
from app.agents.llm import LLMError, LLMUnavailable, agent_runtime


def response(text='{"summary": "ok", "findings": [], "limitations": []}', finish="STOP"):
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=finish)], model_version="gemini-test",
                           usage_metadata=SimpleNamespace(prompt_token_count=120, candidates_token_count=30), response_id="r1")


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def llm(outcomes, sleeps=None):
    client = SimpleNamespace(models=FakeModels(outcomes))
    return GeminiLLM("gemini-test", 30, None, client=client, sleep=(sleeps.append if sleeps is not None else lambda s: None)), client


SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}


def test_parses_structured_json_and_sends_schema_and_system():
    g, client = llm([response()])
    out = g.generate(system="sys", user="evidence", schema=SCHEMA, max_tokens=500)
    assert out["output"]["summary"] == "ok"
    assert out["usage"] == {"input_tokens": 120, "output_tokens": 30}
    cfg = client.models.calls[0]["config"]
    assert cfg.system_instruction == "sys" and cfg.response_json_schema == SCHEMA
    assert cfg.response_mime_type == "application/json" and cfg.max_output_tokens == 500


def test_rate_limit_is_retried_then_succeeds():
    sleeps = []
    g, client = llm([errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}}), response()], sleeps)
    assert g.generate(system="s", user="u", schema=SCHEMA, max_tokens=10)["output"]["summary"] == "ok"
    assert sleeps == [5]


def test_rate_limit_exhausted_is_a_clear_error():
    err = errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    g, _ = llm([err, err, err])
    with pytest.raises(LLMError, match="rate limit"):
        g.generate(system="s", user="u", schema=SCHEMA, max_tokens=10)


def test_bad_key_means_agents_are_skipped_not_failed():
    g, _ = llm([errors.ClientError(400, {"error": {"message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}})])
    with pytest.raises(LLMUnavailable):
        g.generate(system="s", user="u", schema=SCHEMA, max_tokens=10)


def test_truncated_and_invalid_output_are_errors():
    g, _ = llm([response(finish="FinishReason.MAX_TOKENS")])
    with pytest.raises(LLMError, match="truncated"):
        g.generate(system="s", user="u", schema=SCHEMA, max_tokens=10)
    g, _ = llm([response(text="not json")])
    with pytest.raises(LLMError, match="invalid JSON"):
        g.generate(system="s", user="u", schema=SCHEMA, max_tokens=10)


def test_missing_key_is_unavailable():
    with pytest.raises(LLMUnavailable, match="aistudio"):
        GeminiLLM("gemini-test", 30, None)


def settings(**kw):
    base = dict(agent_provider="auto", anthropic_api_key=None, gemini_api_key=None, gemini_model="gemini-x", agent_model="claude-opus-5-5")
    return SimpleNamespace(**(base | kw))


def test_auto_provider_selection(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr("app.agents.llm.Path.home", lambda: __import__("pathlib").Path("/nonexistent-home"))
    assert agent_runtime(settings()) == {"provider": "anthropic", "model": "claude-opus-5-5", "credentials": False}
    assert agent_runtime(settings(gemini_api_key="g")) == {"provider": "gemini", "model": "gemini-x", "credentials": True}
    assert agent_runtime(settings(gemini_api_key="g", anthropic_api_key="a"))["provider"] == "anthropic"
    assert agent_runtime(settings(gemini_api_key="g", anthropic_api_key="a", agent_provider="gemini"))["provider"] == "gemini"


def test_overloaded_model_falls_back_to_the_next_one():
    client = SimpleNamespace(models=FakeModels([
        errors.ServerError(503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}}),
        errors.ServerError(504, {"error": {"message": "deadline", "status": "DEADLINE_EXCEEDED"}}),
        response(),
    ]))
    g = GeminiLLM("gemini-a", 30, None, client=client, sleep=lambda s: None, fallbacks=["gemini-b", "gemini-c", "gemini-a"])
    out = g.generate(system="s", user="u", schema=SCHEMA, max_tokens=10)
    assert [c["model"] for c in client.models.calls] == ["gemini-a", "gemini-b", "gemini-c"]
    assert out["output"]["summary"] == "ok"


def test_all_models_failing_explains_each():
    err = errors.ServerError(503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}})
    client = SimpleNamespace(models=FakeModels([err, err]))
    g = GeminiLLM("gemini-a", 30, None, client=client, sleep=lambda s: None, fallbacks=["gemini-b"])
    with pytest.raises(LLMError, match="gemini-a: 503.*gemini-b: 503"):
        g.generate(system="s", user="u", schema=SCHEMA, max_tokens=10)
