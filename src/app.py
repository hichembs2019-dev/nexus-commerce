"""Wires every piece together from a single Settings - the one place that
decides real vs. mock per external service (spec: a missing secret means
"use mocks and continue", never a crash). Used by both main.py (the long-
running service) and the test suite (which builds an App with every client
forced to a mock regardless of .env, via build_app(..., force_mocks=True)).
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from .agents.agent import AGENT_NAMES, Agent, build_agents
from .config import Settings
from .db.database import init_db
from .integrations.anthropic_client import (
    AgentReasoningClient,
    MockAgentReasoningClient,
    RealAgentReasoningClient,
    RealGeminiReasoningClient,
    RealGroqReasoningClient,
)
from .integrations.cj_client import CJClient, MockCJClient, RealCJClient
from .integrations.shopify_client import MockShopifyClient, RealShopifyClient, ShopifyClient
from .integrations.supplier_client import SupplierRegistry
from .integrations.telegram_client import MockTelegramClient, RealTelegramClient, TelegramClient
from .tools.web_search import MockWebSearchTool, RealWebSearchTool, WebSearchTool
from .workflows.executor import Executor

logger = logging.getLogger("nexus_commerce")


@dataclass
class App:
    settings: Settings
    conn: sqlite3.Connection
    shopify: ShopifyClient
    cj: CJClient
    suppliers: SupplierRegistry
    telegram: TelegramClient
    web_search: WebSearchTool
    agents: list[Agent]
    executor: Executor


def build_app(settings: Settings, *, force_mocks: bool = False) -> App:
    conn = init_db(settings.database_path)

    if not force_mocks and settings.shopify_configured:
        shopify: ShopifyClient = RealShopifyClient(
            settings.shopify_shop_url,
            settings.shopify_client_id,
            settings.shopify_client_secret,
            settings.shopify_api_version,
        )
    else:
        if not force_mocks:
            logger.warning(
                "SHOPIFY_SHOP_URL/SHOPIFY_CLIENT_ID/SHOPIFY_CLIENT_SECRET not set - using MockShopifyClient"
            )
        shopify = MockShopifyClient()

    if not force_mocks and settings.cj_configured:
        cj: CJClient = RealCJClient(settings.cj_api_key, settings.cj_api_base_url)
    else:
        if not force_mocks:
            logger.warning("CJ_API_KEY/CJ_API_BASE_URL not set - using MockCJClient")
        cj = MockCJClient()

    if not force_mocks and settings.telegram_configured:
        telegram: TelegramClient = RealTelegramClient(settings.telegram_bot_token, settings.telegram_chat_id)
    else:
        if not force_mocks:
            logger.warning("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set - using MockTelegramClient")
        telegram = MockTelegramClient()

    # Agent count is len(AGENT_NAMES) in src/agents/agent.py - 1, as of the
    # owner's 2026-10-18 explicit instruction ("اترك وكيل واحد ... الاذكى"
    # - leave one agent, the smartest one): see that module's docstring for
    # the real, measured reason (34/38 real proposals FAILED_CONSENSUS,
    # zero real orders, under the previous 2-agent/free-tier setup).
    agent_count = len(AGENT_NAMES)
    # "الاذكى طبعا" (the smartest, obviously) - Claude (Anthropic) is now
    # the one agent's PRIMARY reasoning provider, not the last resort it
    # was under the old multi-agent/free-tier-first wiring (that order
    # existed to avoid spending real Anthropic balance across several
    # agents' worth of real API calls per round - moot now that there is
    # only one agent and one real call per round). Falls back through
    # Groq then Gemini on a real Anthropic error, same single-agent-own-
    # retry-chain discipline every provider here already uses - never a
    # silent swap to a "dumber" provider unless Anthropic itself failed.
    if not force_mocks and settings.anthropic_configured:
        gemini_fallback = (
            RealGeminiReasoningClient(settings.gemini_api_key, settings.gemini_model)
            if settings.gemini_configured
            else None
        )
        groq_fallback = (
            RealGroqReasoningClient(settings.groq_api_key, settings.groq_model, fallback=gemini_fallback)
            if settings.groq_configured
            else gemini_fallback
        )
        reasoning_clients: list[AgentReasoningClient] = [
            RealAgentReasoningClient(settings.anthropic_api_key, settings.claude_model, fallback=groq_fallback)
            for _ in range(agent_count)
        ]
    elif not force_mocks and settings.groq_configured:
        gemini_fallback = (
            RealGeminiReasoningClient(settings.gemini_api_key, settings.gemini_model)
            if settings.gemini_configured
            else None
        )
        reasoning_clients = [
            RealGroqReasoningClient(settings.groq_api_key, settings.groq_model, fallback=gemini_fallback)
            for _ in range(agent_count)
        ]
    elif not force_mocks and settings.gemini_configured:
        reasoning_clients = [
            RealGeminiReasoningClient(settings.gemini_api_key, settings.gemini_model) for _ in range(agent_count)
        ]
    else:
        if not force_mocks:
            logger.warning("Neither ANTHROPIC_API_KEY nor GROQ_API_KEY nor GEMINI_API_KEY set - using MockAgentReasoningClient for every agent")
        reasoning_clients = [MockAgentReasoningClient() for _ in range(agent_count)]
    agents = build_agents(reasoning_clients)

    if not force_mocks and settings.anthropic_configured:
        # Web search is still Anthropic-only (see docs/SOURCES.md "Web
        # search tool") - independent of which provider runs the 5 agents.
        web_search: WebSearchTool = RealWebSearchTool(settings.anthropic_api_key, settings.claude_model)
    else:
        if not force_mocks:
            logger.warning("ANTHROPIC_API_KEY not set - using MockWebSearchTool")
        web_search = MockWebSearchTool()

    # Only "cj" has any real-path potential today (see docs/UNVERIFIED.md);
    # the registry exists so new_product_discovery.py can search additional
    # suppliers the moment anyone registers one - no code change needed
    # there, only here.
    suppliers = SupplierRegistry({"cj": cj})
    executor = Executor(shopify, suppliers, settings)

    return App(
        settings=settings,
        conn=conn,
        shopify=shopify,
        cj=cj,
        suppliers=suppliers,
        telegram=telegram,
        web_search=web_search,
        agents=agents,
        executor=executor,
    )
