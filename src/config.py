"""Loads .env once and exposes every setting as a typed attribute of a single
Settings instance - no module reaches into os.environ directly, so tests can
construct a Settings() with explicit values instead of mutating process
environment variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _float(value: str | None, default: float) -> float:
    if value is None or value == "":
        return default
    return float(value)


@dataclass
class Settings:
    # Anthropic
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5-5"

    # Shopify
    shopify_shop_url: str = ""
    shopify_access_token: str = ""
    shopify_api_version: str = "2024-07"
    # The store's real currency was never confirmed (see docs/SOURCES.md
    # "productCreate with images") - a simple, overridable default, not a
    # verified fact about any specific store.
    shopify_currency_code: str = "USD"

    # CJ Dropshipping - base URL verified 2026-10-11, see docs/SOURCES.md
    # "CJ Dropshipping > Authentication".
    cj_api_key: str = ""
    cj_api_base_url: str = "https://developers.cjdropshipping.com/api2.0/v1"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Safety limits (spec SS4)
    max_order_cost: float = 200.0
    daily_spend_limit: float = 500.0
    min_margin: float = 0.25

    # Mode
    dry_run: bool = True

    # Misc
    database_path: str = "./nexus_commerce.db"
    hourly_interval_minutes: int = 60
    log_level: str = "INFO"

    @property
    def shopify_configured(self) -> bool:
        return bool(self.shopify_shop_url and self.shopify_access_token)

    @property
    def cj_configured(self) -> bool:
        return bool(self.cj_api_key and self.cj_api_base_url)

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)


def load_settings(env_path: str | Path | None = None) -> Settings:
    """Loads .env (if present) then reads os.environ. A missing .env is not
    an error - spec SS4/SS6: a missing secret means "use mocks and continue",
    never a crash. Pass env_path explicitly in tests instead of relying on
    cwd.
    """
    if env_path is not None:
        load_dotenv(env_path, override=False)
    else:
        load_dotenv(override=False)

    return Settings(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        claude_model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"),
        shopify_shop_url=os.environ.get("SHOPIFY_SHOP_URL", ""),
        shopify_access_token=os.environ.get("SHOPIFY_ACCESS_TOKEN", ""),
        shopify_api_version=os.environ.get("SHOPIFY_API_VERSION", "2024-07"),
        shopify_currency_code=os.environ.get("SHOPIFY_CURRENCY_CODE", "USD"),
        cj_api_key=os.environ.get("CJ_API_KEY", ""),
        cj_api_base_url=os.environ.get("CJ_API_BASE_URL", "https://developers.cjdropshipping.com/api2.0/v1"),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        max_order_cost=_float(os.environ.get("MAX_ORDER_COST"), 200.0),
        daily_spend_limit=_float(os.environ.get("DAILY_SPEND_LIMIT"), 500.0),
        min_margin=_float(os.environ.get("MIN_MARGIN"), 0.25),
        dry_run=_bool(os.environ.get("DRY_RUN"), True),
        database_path=os.environ.get("DATABASE_PATH", "./nexus_commerce.db"),
        hourly_interval_minutes=int(os.environ.get("HOURLY_INTERVAL_MINUTES", "60")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
