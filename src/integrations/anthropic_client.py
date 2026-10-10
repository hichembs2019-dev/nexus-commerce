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
