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
    RealGeminiReasoningClient,
    RealGroqReasoningClient,
)
from .integrations.cj_client import CJClient, MockCJClient, RealCJClient
from .integrations.marketing_client import (
    MarketingClient,
    MarketingRegistry,
    RealFacebookPageClient,
    RealInstagramClient,
    RealTelegramChannelClient,
)
from .integrations.shopify_client import MockShopifyClient, RealShopifyClient, ShopifyClient
from .integrations.supplier_client import SupplierRegistry
from .integrations.telegram_client import MockTelegramClient, RealTelegramClient, TelegramClient
from .tools.web_search import MockWebSearchTool, WebSearchTool
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
    marketing: MarketingRegistry
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
    # Owner's explicit instruction, 2026-10-18 ("احذف كلود لانه ليس
    # مجاني" - remove Claude, it isn't free): Anthropic is OUT of this
    # agent's reasoning chain entirely, reverted to the free-tier-first
    # order (Groq primary, Gemini its fallback) this project used before
    # "الاذكى طبعا" briefly put Claude first the same day. Only real cost
    # here now is whatever Groq/Gemini's own free tiers don't cover -
    # Claude is not instantiated for this at all, configured or not.
    if not force_mocks and settings.groq_configured:
        gemini_fallback = (
            RealGeminiReasoningClient(settings.gemini_api_key, settings.gemini_model)
            if settings.gemini_configured
            else None
        )
        reasoning_clients: list[AgentReasoningClient] = [
            RealGroqReasoningClient(settings.groq_api_key, settings.groq_model, fallback=gemini_fallback)
            for _ in range(agent_count)
        ]
    elif not force_mocks and settings.gemini_configured:
        reasoning_clients = [
            RealGeminiReasoningClient(settings.gemini_api_key, settings.gemini_model) for _ in range(agent_count)
        ]
    else:
        if not force_mocks:
            logger.warning("Neither GROQ_API_KEY nor GEMINI_API_KEY set - using MockAgentReasoningClient for every agent (Claude is deliberately excluded here, see owner's 2026-10-18 instruction)")
        reasoning_clients = [MockAgentReasoningClient() for _ in range(agent_count)]
    agents = build_agents(reasoning_clients)

    # Owner's instruction, 2026-10-18 ("اترك المجاني و بس" - leave only
    # the free one): the only real web-search implementation this project
    # has is Anthropic's own server-side tool (see docs/SOURCES.md "Web
    # search tool") - there is no free provider for it here. Rather than
    # silently keep spending real Anthropic money on the one real
    # implementation available, this always uses MockWebSearchTool now
    # (no real competitor-price search), honestly logged as the real
    # trade-off it is - not a quiet downgrade. Real web search for
    # new_product_discovery.py's competitor research needs either a real
    # Anthropic key spend decision from the owner, or a different, free
    # search provider plugged in here later.
    if not force_mocks:
        logger.warning("Web search disabled (owner's 2026-10-18 free-only instruction) - using MockWebSearchTool, no real competitor-price search")
    web_search: WebSearchTool = MockWebSearchTool()

    # Only "cj" has any real-path potential today (see docs/UNVERIFIED.md);
    # the registry exists so new_product_discovery.py can search additional
    # suppliers the moment anyone registers one - no code change needed
    # there, only here.
    suppliers = SupplierRegistry({"cj": cj})
    executor = Executor(shopify, suppliers, settings)

    # Marketing - each platform independently optional (see
    # integrations/marketing_client.py and config.py's own docstrings for
    # why these three and not X/Pinterest). An empty registry is a real,
    # valid state (nothing configured yet) - workflows/pipeline.py's
    # _promote_if_published() already treats len(registry) == 0 as "nothing
    # to do", not an error, so this never needs a Mock fallback the way the
    # other integrations above do.
    marketing_platforms: dict[str, MarketingClient] = {}
    if not force_mocks and settings.telegram_marketing_configured:
        marketing_platforms["telegram"] = RealTelegramChannelClient(
            settings.telegram_bot_token, settings.telegram_marketing_channel_id
        )
    if not force_mocks and settings.facebook_configured:
        marketing_platforms["facebook"] = RealFacebookPageClient(
            settings.facebook_page_id, settings.facebook_page_access_token
        )
    if not force_mocks and settings.instagram_configured:
        marketing_platforms["instagram"] = RealInstagramClient(
            settings.instagram_business_account_id, settings.facebook_page_access_token
        )
    if not force_mocks and not marketing_platforms:
        logger.warning(
            "No marketing platform configured (TELEGRAM_MARKETING_CHANNEL_ID/FACEBOOK_*/INSTAGRAM_*) "
            "- published products will not be promoted anywhere"
        )
    marketing = MarketingRegistry(marketing_platforms)

    return App(
        settings=settings,
        conn=conn,
        shopify=shopify,
        cj=cj,
        suppliers=suppliers,
        telegram=telegram,
        web_search=web_search,
        marketing=marketing,
        agents=agents,
        executor=executor,
    )
