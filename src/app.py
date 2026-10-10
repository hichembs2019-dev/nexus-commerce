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

from .agents.agent import Agent, build_five_agents
from .config import Settings
from .db.database import init_db
from .integrations.anthropic_client import (
    AgentReasoningClient,
    MockAgentReasoningClient,
    RealAgentReasoningClient,
)
from .integrations.cj_client import CJClient, MockCJClient, RealCJClient
from .integrations.shopify_client import MockShopifyClient, RealShopifyClient, ShopifyClient
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
    telegram: TelegramClient
    web_search: WebSearchTool
    agents: list[Agent]
    executor: Executor


def build_app(settings: Settings, *, force_mocks: bool = False) -> App:
    conn = init_db(settings.database_path)

    if not force_mocks and settings.shopify_configured:
        shopify: ShopifyClient = RealShopifyClient(
            settings.shopify_shop_url, settings.shopify_access_token, settings.shopify_api_version
        )
    else:
        if not force_mocks:
            logger.warning("SHOPIFY_SHOP_URL/SHOPIFY_ACCESS_TOKEN not set - using MockShopifyClient")
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

    web_search: WebSearchTool = MockWebSearchTool() if force_mocks else RealWebSearchTool()

    if not force_mocks and settings.anthropic_configured:
        reasoning_clients: list[AgentReasoningClient] = [
            RealAgentReasoningClient(settings.anthropic_api_key, settings.claude_model) for _ in range(5)
        ]
    else:
        if not force_mocks:
            logger.warning("ANTHROPIC_API_KEY not set - using MockAgentReasoningClient for all 5 agents")
        reasoning_clients = [MockAgentReasoningClient() for _ in range(5)]
    agents = build_five_agents(reasoning_clients)

    executor = Executor(shopify, cj, settings)

    return App(
        settings=settings,
        conn=conn,
        shopify=shopify,
        cj=cj,
        telegram=telegram,
        web_search=web_search,
        agents=agents,
        executor=executor,
    )
