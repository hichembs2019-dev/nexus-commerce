"""Owner's instruction, 2026-10-18 ("اترك groq يشتغل كل شيء لوحده و
جيميني يبحث على التسويق" - leave Groq to run everything alone, Gemini
works on marketing): build_app() must wire Groq with NO Gemini fallback
for the agents' own decision reasoning, and a separate, dedicated Gemini
client for marketing copy only. Nothing else in this project's test
suite exercises build_app()'s real (non-mock) reasoning-client wiring at
all - this is the only place that would catch the two providers being
mixed back together.
"""
from __future__ import annotations

from src.app import build_app
from src.config import Settings
from src.integrations.anthropic_client import RealGeminiReasoningClient, RealGroqReasoningClient


def _real_settings(**overrides) -> Settings:
    base = dict(
        groq_api_key="fake-groq-key",
        groq_model="openai/gpt-oss-120b",
        gemini_api_key="fake-gemini-key",
        gemini_model="gemma-4-26b-a4b-it",
        database_path=":memory:",
    )
    base.update(overrides)
    return Settings(**base)


def test_groq_runs_agent_reasoning_alone_with_no_gemini_fallback():
    settings = _real_settings()

    app = build_app(settings)

    reasoning_client = app.agents[0].reasoning_client
    assert isinstance(reasoning_client, RealGroqReasoningClient)
    assert reasoning_client._fallback is None


def test_gemini_is_wired_as_its_own_dedicated_marketing_client_not_shared_with_agents():
    settings = _real_settings()

    app = build_app(settings)

    assert isinstance(app.marketing_reasoning_client, RealGeminiReasoningClient)
    # Never the same object as any agent's own reasoning client - the two
    # providers' roles are fully separate, not aliased to look separate.
    assert app.marketing_reasoning_client is not app.agents[0].reasoning_client


def test_with_only_gemini_configured_it_still_covers_agent_reasoning_standalone():
    settings = _real_settings(groq_api_key="")

    app = build_app(settings)

    assert isinstance(app.agents[0].reasoning_client, RealGeminiReasoningClient)
