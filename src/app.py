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

from .agents.agent import AGENT_NAMES, Agent, build_five_agents
from .config import Settings
from .db.database import init_db
from .integrations.anthropic_client import (
    AgentReasoningClient,
    MockAgentReasoningClient,
    RealAgentReasoningClient,
    RealGeminiReasoningClient,
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
            settings.shopify_currency_code,
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

    # consensus.py requires MIN_APPROVALS real "approve" votes out of
    # len(agents) (run_consensus), and any agent whose reasoning call errors
    # auto-degrades to a permanent "reject" (_review_with_fallback) - never
    # a crash, but also never a vote, for as long as that one agent's
    # provider keeps failing. So mixing a broken provider in is not a safe
    # way to "diversify" - found live 2026-10-13 when the Anthropic account
    # ran out of credit mid-run and every proposal then failed consensus
    # silently. Gemini (free, verified working live) runs every agent
    # whenever it's configured, not split with Anthropic, so a real vote
    # can actually complete. See docs/SOURCES.md "Gemini agent reasoning"
    # for the live proof and how to mix them again once both are confirmed
    # healthy (change the two zip()'d lists below).
    #
    # Agent count is len(AGENT_NAMES) in src/agents/agent.py (2, as of the
    # owner's 2026-10-14 experiment - see that module's docstring).
    agent_count = len(AGENT_NAMES)
    if not force_mocks and settings.gemini_configured:
        reasoning_clients: list[AgentReasoningClient] = [
            RealGeminiReasoningClient(settings.gemini_api_key, settings.gemini_model) for _ in range(agent_count)
        ]
    elif not force_mocks and settings.anthropic_configured:
        reasoning_clients = [
            RealAgentReasoningClient(settings.anthropic_api_key, settings.claude_model) for _ in range(agent_count)
        ]
    else:
        if not force_mocks:
            logger.warning("Neither GEMINI_API_KEY nor ANTHROPIC_API_KEY set - using MockAgentReasoningClient for every agent")
        reasoning_clients = [MockAgentReasoningClient() for _ in range(agent_count)]
    agents = build_five_agents(reasoning_clients)

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
