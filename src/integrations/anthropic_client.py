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
    """Owner's explicit choice as THE single agent's primary reasoning
    provider (2026-10-18, "الاذكى طبعا" - the smartest one, obviously):
    see src/app.py's build_app() for the real provider order this now
    drives. `fallback` mirrors the same single-call-extends-its-own-retry-
    chain pattern RealGroqReasoningClient/RealGeminiReasoningClient
    already use, so one agent that IS the whole decision doesn't go
    silent-reject on a single transient Anthropic API error.
    """

    def __init__(self, api_key: str, model: str, fallback: AgentReasoningClient | None = None):
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._fallback = fallback

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return "".join(block.text for block in message.content if hasattr(block, "text"))
        except Exception:
            if self._fallback is not None:
                return self._fallback.complete(system_prompt, user_prompt)
            raise


class RealGeminiReasoningClient(AgentReasoningClient):
    """A second, independent reasoning backend - verified 2026-10-13, see
    docs/SOURCES.md "Gemini agent reasoning". Lets the 5 agents genuinely
    diversify which model backs each vote (the owner's own request: several
    free providers working together, not one model talking to itself under
    five labels), using Google's free-tier API key rather than spending more
    of the Anthropic balance.
    """

    def __init__(self, api_key: str, model: str, fallback: AgentReasoningClient | None = None):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model
        # Owner's own real key, added live 2026-10-14 right after Gemini's
        # real error rate spiked (see docs/SOURCES.md "Groq fallback").
        # Since 2026-10-15 Gemini is no longer the primary provider (see
        # RealGroqReasoningClient's own docstring) - this `fallback` is now
        # used only when Gemini itself is deliberately selected as primary
        # (e.g. Groq not configured). Never mixed mid-round the way
        # src/app.py already documents not mixing Gemini/Anthropic - this
        # is the SAME agent's own call falling back, not a different agent
        # using a different provider.
        self._fallback = fallback

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
        if self._fallback is not None:
            return self._fallback.complete(system_prompt, user_prompt)
        raise last_error


class RealGroqReasoningClient(AgentReasoningClient):
    """Verified live 2026-10-14 - a real POST to
    https://api.groq.com/openai/v1/chat/completions with the owner's real
    key returned a real 200 and the standard OpenAI-compatible
    choices[0].message.content shape (confirmed against the real
    /v1/models list first - "llama-3.3-70b-versatile" doesn't exist for
    this key, "openai/gpt-oss-120b" does).

    Owner's explicit instruction, 2026-10-15, after watching the real
    production logs: Gemini's real error rate (500s and 429s) was so high
    that Groq - which answered 200 OK every single time in that same
    window - was carrying almost every real vote anyway through
    RealGeminiReasoningClient's own fallback. "ضع جيميني احتياطي و استعمل
    الاخر" (make Gemini the backup, use the other one) - so the roles are
    swapped: Groq is primary (see src/app.py), with Gemini as ITS fallback
    now, via the same `fallback` pattern Gemini already used the other way
    around. Still never a different provider for a different agent
    mid-round - the same single-agent-call-extends-its-own-retry-chain
    discipline documented on RealGeminiReasoningClient below.
    """

    def __init__(self, api_key: str, model: str, fallback: AgentReasoningClient | None = None):
        self._api_key = api_key
        self._model = model
        self._fallback = fallback

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        import httpx

        try:
            response = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=30,
            )
            payload = response.json()
            if "error" in payload:
                raise RuntimeError(f"Groq completion failed: {payload['error'].get('message')}")
            return payload["choices"][0]["message"]["content"] or ""
        except Exception:
            if self._fallback is not None:
                return self._fallback.complete(system_prompt, user_prompt)
            raise


class RealSambaNovaReasoningClient(AgentReasoningClient):
    """SambaNova Cloud - OpenAI-compatible chat completions API, same
    request/response shape as RealGroqReasoningClient above (confirmed via
    SambaNova's own docs, docs.sambanova.ai/docs/en/features/openai-
    compatibility: POST https://api.sambanova.ai/v1/chat/completions,
    Bearer auth, {"model":, "messages":[...]}, choices[0].message.content).

    Owner's instruction, 2026-10-18 ("اذا كان يجب ان نضيف اخر مع groq
    نبحث على المجاني" - if we need to add another alongside Groq, look for
    a free one): added as Groq's own fallback for agent decision reasoning
    specifically (src/app.py) - Gemini stays fully separate, dedicated to
    marketing copy only (see that module's own comment), never mixed back
    into this chain.

    NOT yet live-verified against a real key - the live /v1/models check
    this project used for Groq (confirming "openai/gpt-oss-120b" exists
    for that key before trusting it) was blocked by this session's own
    safety classifier for a raw curl with a bearer token. The default
    model below ("Meta-Llama-3.3-70B-Instruct") is the name most
    consistently cited across SambaNova's own release notes and several
    third-party integration docs as of 2026-10, not a guess invented here
    - but it is UNCONFIRMED against this specific key. SAMBANOVA_MODEL is
    a real env var specifically so the owner can correct this from their
    own dashboard without a code change if it's wrong.
    """

    def __init__(self, api_key: str, model: str, fallback: AgentReasoningClient | None = None):
        self._api_key = api_key
        self._model = model
        self._fallback = fallback

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        import httpx

        try:
            response = httpx.post(
                "https://api.sambanova.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=30,
            )
            payload = response.json()
            if "error" in payload:
                raise RuntimeError(f"SambaNova completion failed: {payload['error'].get('message')}")
            return payload["choices"][0]["message"]["content"] or ""
        except Exception:
            if self._fallback is not None:
                return self._fallback.complete(system_prompt, user_prompt)
            raise


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
