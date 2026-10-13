"""Agent reasoning - the one external call every one of the 5 agents makes.
Verified usage: docs/SOURCES.md "Anthropic (Claude)". The exact shape of a
response's `.content` (a list of content blocks, each with `.text` for plain
text) is standard, stable Anthropic SDK behavior present in every public
example since the SDK's first release - not independently re-fetched this
session beyond the client-instantiation pattern that was, but flagged here
rather than silently treated as equally verified.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class AgentReasoningClient(ABC):
    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """One request/response turn: system prompt + the full context an
        agent needs (the proposal, prior votes if any), returns the model's
        raw text reply for the caller to parse as a vote.
        """


class RealAgentReasoningClient(AgentReasoningClient):
    def __init__(self, api_key: str, model: str):
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self._model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in message.content if hasattr(block, "text"))


class RealGeminiReasoningClient(AgentReasoningClient):
    """A second, independent reasoning backend - verified 2026-10-13, see
    docs/SOURCES.md "Gemini agent reasoning". Lets the 5 agents genuinely
    diversify which model backs each vote (the owner's own request: several
    free providers working together, not one model talking to itself under
    five labels), using Google's free-tier API key rather than spending more
    of the Anthropic balance.
    """

    def __init__(self, api_key: str, model: str):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    # Found live 2026-10-13 (see docs/SOURCES.md): roughly half of real
    # calls to gemma-4-26b-a4b-it came back `500 Internal Server Error` -
    # transient, not a request-shape problem (the same call retried plain
    # succeeds). consensus.py requires a UNANIMOUS approve from all 5
    # agents, so a ~50% per-call failure rate makes a full round nearly
    # impossible to ever pass with no retry. A separate live run then hit
    # `429 Too Many Requests` (the free tier's own rate limit, not a
    # transient server fault) - a 500/503 is retried fast since the server
    # is just flaky, but a 429 needs to actually wait out the quota window,
    # so it gets its own longer delay rather than reusing the short one.
    _MAX_RETRIES = 3
    _RETRY_DELAY_SECONDS = 2
    _RATE_LIMIT_RETRY_DELAY_SECONDS = 20

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        from google.genai import errors

        # The system_instruction config field 500s on Gemma models (found
        # live, 2026-10-13 - see docs/SOURCES.md) - folding the system
        # prompt into contents instead works on both Gemini and Gemma, so
        # this path makes no model-family assumption.
        contents = f"{system_prompt}\n\n{user_prompt}"
        last_error: Exception | None = None
        for attempt in range(self._MAX_RETRIES):
            try:
                response = self._client.models.generate_content(model=self._model, contents=contents)
                return response.text or ""
            except (errors.ServerError, errors.ClientError) as exc:
                is_rate_limit = getattr(exc, "code", None) == 429
                if not isinstance(exc, errors.ServerError) and not is_rate_limit:
                    raise  # a non-429 client error (bad request, auth, ...) is not transient
                last_error = exc
                if attempt < self._MAX_RETRIES - 1:
                    import time

                    time.sleep(self._RATE_LIMIT_RETRY_DELAY_SECONDS if is_rate_limit else self._RETRY_DELAY_SECONDS)
        raise last_error


class MockAgentReasoningClient(AgentReasoningClient):
    """Returns scripted replies in order, one per call - lets a test drive
    exactly what each of the 5 agents "says" on each round without any real
    API access. Raises if asked for more replies than scripted, rather than
    silently looping, so a test's agent count always matches what it meant
    to script.
    """

    def __init__(self, scripted_replies: list[str] | None = None):
        self._replies = list(scripted_replies or [])
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if not self._replies:
            raise AssertionError("MockAgentReasoningClient ran out of scripted replies")
        return self._replies.pop(0)
