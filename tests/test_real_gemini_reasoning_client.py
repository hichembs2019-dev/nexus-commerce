"""Unit tests for RealGeminiReasoningClient - verified 2026-10-13, see
docs/SOURCES.md "Gemini agent reasoning". The real google.genai.Client()
call is faked here (it needs a real API call); everything above that is
real project code.
"""
from __future__ import annotations

from src.integrations.anthropic_client import RealGeminiReasoningClient


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text


def _client(monkeypatch, response_text: str) -> tuple[RealGeminiReasoningClient, list]:
    calls = []

    class _FakeModels:
        def generate_content(self, *, model, contents):
            calls.append({"model": model, "contents": contents})
            return _FakeResponse(response_text)

    class _FakeClient:
        def __init__(self, *, api_key):
            self.models = _FakeModels()

    from google import genai

    monkeypatch.setattr(genai, "Client", _FakeClient)

    client = RealGeminiReasoningClient(api_key="fake-key", model="gemma-4-26b-a4b-it")
    return client, calls


def test_complete_folds_the_system_prompt_into_contents(monkeypatch):
    # system_instruction 500s on Gemma models (found live, 2026-10-13) -
    # the system prompt is folded into contents instead, which works on
    # both Gemini and Gemma.
    client, calls = _client(monkeypatch, '{"vote": "approve", "reason": "ok"}')

    result = client.complete("You are agent A1.", "Review this proposal: ...")

    assert len(calls) == 1
    call = calls[0]
    assert call["model"] == "gemma-4-26b-a4b-it"
    assert call["contents"] == "You are agent A1.\n\nReview this proposal: ..."
    assert result == '{"vote": "approve", "reason": "ok"}'


def test_complete_returns_empty_string_when_the_response_has_no_text(monkeypatch):
    client, _ = _client(monkeypatch, None)

    assert client.complete("sys", "user") == ""


def test_complete_retries_a_transient_server_error_and_then_succeeds(monkeypatch):
    # Found live 2026-10-13: ~50% of real gemma-4-26b-a4b-it calls came back
    # 500 Internal Server Error, transient - the same request retried plain
    # succeeds. Without a retry, consensus.py's unanimous-approve
    # requirement across all 5 agents is nearly unreachable.
    from google.genai import errors

    call_count = 0

    class _FakeModels:
        def generate_content(self, *, model, contents):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise errors.ServerError(500, {"error": {"message": "Internal error"}})
            return _FakeResponse('{"vote": "approve", "reason": "ok"}')

    class _FakeClient:
        def __init__(self, *, api_key):
            self.models = _FakeModels()

    from google import genai

    monkeypatch.setattr(genai, "Client", _FakeClient)
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    client = RealGeminiReasoningClient(api_key="fake-key", model="gemma-4-26b-a4b-it")
    result = client.complete("sys", "user")

    assert call_count == 3
    assert result == '{"vote": "approve", "reason": "ok"}'


def test_complete_raises_after_exhausting_all_retries(monkeypatch):
    from google.genai import errors

    call_count = 0

    class _FakeModels:
        def generate_content(self, *, model, contents):
            nonlocal call_count
            call_count += 1
            raise errors.ServerError(500, {"error": {"message": "Internal error"}})

    class _FakeClient:
        def __init__(self, *, api_key):
            self.models = _FakeModels()

    from google import genai

    monkeypatch.setattr(genai, "Client", _FakeClient)
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    client = RealGeminiReasoningClient(api_key="fake-key", model="gemma-4-26b-a4b-it")

    import pytest

    with pytest.raises(errors.ServerError):
        client.complete("sys", "user")

    assert call_count == 3


def test_complete_retries_a_429_rate_limit_with_the_longer_delay(monkeypatch):
    # Found live 2026-10-13: a real run hit 429 Too Many Requests (the free
    # tier's own quota), distinct from the 500s above - it needs the longer
    # rate-limit delay, not the short transient-error one.
    from google.genai import errors

    call_count = 0
    sleep_calls = []

    class _FakeModels:
        def generate_content(self, *, model, contents):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise errors.ClientError(429, {"error": {"message": "rate limited"}})
            return _FakeResponse('{"vote": "approve", "reason": "ok"}')

    class _FakeClient:
        def __init__(self, *, api_key):
            self.models = _FakeModels()

    from google import genai

    monkeypatch.setattr(genai, "Client", _FakeClient)
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    client = RealGeminiReasoningClient(api_key="fake-key", model="gemma-4-26b-a4b-it")
    result = client.complete("sys", "user")

    assert call_count == 2
    assert sleep_calls == [20]
    assert result == '{"vote": "approve", "reason": "ok"}'


def test_complete_does_not_retry_a_non_rate_limit_client_error(monkeypatch):
    # A 400 (bad request) or 401/403 (auth) is a real, non-transient bug -
    # retrying it would just waste the free quota on the same failure.
    from google.genai import errors

    call_count = 0

    class _FakeModels:
        def generate_content(self, *, model, contents):
            nonlocal call_count
            call_count += 1
            raise errors.ClientError(400, {"error": {"message": "bad request"}})

    class _FakeClient:
        def __init__(self, *, api_key):
            self.models = _FakeModels()

    from google import genai

    monkeypatch.setattr(genai, "Client", _FakeClient)
    monkeypatch.setattr("time.sleep", lambda seconds: (_ for _ in ()).throw(AssertionError("should not sleep")))

    client = RealGeminiReasoningClient(api_key="fake-key", model="gemma-4-26b-a4b-it")

    import pytest

    with pytest.raises(errors.ClientError):
        client.complete("sys", "user")

    assert call_count == 1
