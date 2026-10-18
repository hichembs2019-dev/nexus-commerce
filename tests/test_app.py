"""Owner's instruction, 2026-10-18 ("اترك groq يشتغل كل شيء لوحده و
جيميني يبحث على التسويق" - leave Groq to run everything alone, Gemini
works on marketing): build_app() must wire Groq with NO Gemini fallback
for the agents' own decision reasoning, and a separate, dedicated Gemini
client for marketing copy only.

Same day, follow-up instruction ("اذا كان يجب ان نضيف اخر مع groq نبحث
على المجاني" - if another is needed alongside Groq, find a free one):
SambaNova is Groq's own fallback for this chain now - still never
Gemini.

Nothing else in this project's test suite exercises build_app()'s real
(non-mock) reasoning-client wiring at all - this is the only place that
would catch the providers being mixed back together wrong.
"""
from __future__ import annotations

from src.app import build_app
from src.config import Settings
from src.integrations.anthropic_client import (
    RealGeminiReasoningClient,
    RealGroqReasoningClient,
    RealSambaNovaReasoningClient,
)


def _real_settings(**overrides) -> Settings:
    base = dict(
        groq_api_key="fake-groq-key",
        groq_model="openai/gpt-oss-120b",
        sambanova_api_key="fake-sambanova-key",
        sambanova_model="Meta-Llama-3.3-70B-Instruct",
        gemini_api_key="fake-gemini-key",
        gemini_model="gemma-4-26b-a4b-it",
        database_path=":memory:",
    )
    base.update(overrides)
    return Settings(**base)


def test_groq_runs_agent_reasoning_with_sambanova_as_its_fallback_never_gemini():
    settings = _real_settings()

    app = build_app(settings)

    reasoning_client = app.agents[0].reasoning_client
    assert isinstance(reasoning_client, RealGroqReasoningClient)
    assert isinstance(reasoning_client._fallback, RealSambaNovaReasoningClient)


def test_groq_has_no_fallback_at_all_when_sambanova_is_not_configured():
    settings = _real_settings(sambanova_api_key="")

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


def test_with_only_sambanova_configured_it_covers_agent_reasoning_standalone():
    settings = _real_settings(groq_api_key="")

    app = build_app(settings)

    assert isinstance(app.agents[0].reasoning_client, RealSambaNovaReasoningClient)


def test_with_only_gemini_configured_it_still_covers_agent_reasoning_standalone():
    settings = _real_settings(groq_api_key="", sambanova_api_key="")

    app = build_app(settings)

    assert isinstance(app.agents[0].reasoning_client, RealGeminiReasoningClient)
