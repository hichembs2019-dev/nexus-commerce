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


def _str(value: str | None, default: str) -> str:
    """Like os.environ.get's default, but also falls back when the .env key
    is present but left blank (e.g. `CJ_API_BASE_URL=`) - a key that exists
    in the file always wins over the Python default otherwise, even empty.
    Only for fields with a real non-empty default (base URLs, versions) -
    pure secrets (API keys/tokens) correctly stay "" when unset.
    """
    if value is None or value == "":
        return default
    return value


@dataclass
class Settings:
    # Anthropic
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5-5"

    # Gemini - a second, independent reasoning backend (owner's own request:
    # several free providers working together) - verified 2026-10-13, see
    # docs/SOURCES.md "Gemini agent reasoning".
    gemini_api_key: str = ""
    gemini_model: str = "gemma-4-26b-a4b-it"

    # Groq - verified live 2026-10-14, see docs/SOURCES.md "Groq fallback".
    # Owner's instruction, 2026-10-18 ("اترك groq يشتغل كل شيء لوحده و
    # جيميني يبحث على التسويق"): Groq runs the agents' own decision
    # reasoning when configured, with Gemini removed from this chain
    # entirely (no mid-decision switch to Gemini any more - see
    # src/app.py; Gemini is its own separate client, used only for
    # marketing copy). SambaNova (below) is Groq's own fallback for THIS
    # chain instead, same owner instruction, same day ("اذا كان يجب ان
    # نضيف اخر مع groq نبحث على المجاني" - if another is needed alongside
    # Groq, look for a free one).
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    # SambaNova - Groq's own fallback for agent decision reasoning (see
    # the Groq comment above and src/app.py). OpenAI-compatible API,
    # verified against SambaNova's own docs - see
    # integrations/anthropic_client.py's RealSambaNovaReasoningClient
    # docstring for what is and is not confirmed. Get a free key (no
    # payment method required) from cloud.sambanova.ai -> API Keys.
    sambanova_api_key: str = ""
    sambanova_model: str = "Meta-Llama-3.3-70B-Instruct"

    # Shopify - Client credentials grant (verified 2026-10-12, see
    # docs/SOURCES.md "Shopify > Client credentials access token"): the app
    # exchanges its own Client ID + Secret for an access token itself, no
    # manually-obtained static token.
    shopify_shop_url: str = ""
    shopify_client_id: str = ""
    shopify_client_secret: str = ""
    shopify_api_version: str = "2024-07"

    # CJ Dropshipping - base URL verified 2026-10-11, see docs/SOURCES.md
    # "CJ Dropshipping > Authentication".
    cj_api_key: str = ""
    cj_api_base_url: str = "https://developers.cjdropshipping.com/api2.0/v1"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Marketing - real platform posting after a real product publish, owner's
    # 2026-10-18 instruction ("ابحث انت و قرر الافضل"). Each is independently
    # optional (integrations/marketing_client.py's MarketingRegistry only
    # includes the platforms actually configured). Uses the SAME bot token as
    # telegram_bot_token above, posted to a different chat_id (a public
    # channel, not the owner's private approval chat).
    telegram_marketing_channel_id: str = ""
    # Facebook Page + Instagram share one Meta access token (see
    # docs/SOURCES.md "Marketing - real platform research").
    facebook_page_id: str = ""
    facebook_page_access_token: str = ""
    instagram_business_account_id: str = ""

    # Pricing (spec SS4/SS6). Owner's explicit instruction, 2026-10-14:
    # MAX_ORDER_COST/DAILY_SPEND_LIMIT are removed entirely - see
    # tools/limits.py's module docstring for why that is safe, not just
    # permitted. MIN_MARGIN is no longer a reject-gate floor (any real
    # positive profit passes, see tools/limits.py's check_margin()) - it
    # survives only as price_inventory_review.py's own repricing target.
    min_margin: float = 0.25

    # Mode
    dry_run: bool = True

    # Misc
    database_path: str = "./nexus_commerce.db"
    hourly_interval_minutes: int = 60
    log_level: str = "INFO"

    @property
    def shopify_configured(self) -> bool:
        return bool(self.shopify_shop_url and self.shopify_client_id and self.shopify_client_secret)

    @property
    def cj_configured(self) -> bool:
        return bool(self.cj_api_key and self.cj_api_base_url)

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def sambanova_configured(self) -> bool:
        return bool(self.sambanova_api_key)

    @property
    def telegram_marketing_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_marketing_channel_id)

    @property
    def facebook_configured(self) -> bool:
        return bool(self.facebook_page_id and self.facebook_page_access_token)

    @property
    def instagram_configured(self) -> bool:
        return bool(self.instagram_business_account_id and self.facebook_page_access_token)


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
        claude_model=_str(os.environ.get("CLAUDE_MODEL"), "claude-sonnet-5-5"),
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        gemini_model=_str(os.environ.get("GEMINI_MODEL"), "gemma-4-26b-a4b-it"),
        groq_api_key=os.environ.get("GROQ_API_KEY", ""),
        groq_model=_str(os.environ.get("GROQ_MODEL"), "openai/gpt-oss-120b"),
        sambanova_api_key=os.environ.get("SAMBANOVA_API_KEY", ""),
        sambanova_model=_str(os.environ.get("SAMBANOVA_MODEL"), "Meta-Llama-3.3-70B-Instruct"),
        shopify_shop_url=os.environ.get("SHOPIFY_SHOP_URL", ""),
        shopify_client_id=os.environ.get("SHOPIFY_CLIENT_ID", ""),
        shopify_client_secret=os.environ.get("SHOPIFY_CLIENT_SECRET", ""),
        shopify_api_version=_str(os.environ.get("SHOPIFY_API_VERSION"), "2024-07"),
        cj_api_key=os.environ.get("CJ_API_KEY", ""),
        cj_api_base_url=_str(
            os.environ.get("CJ_API_BASE_URL"), "https://developers.cjdropshipping.com/api2.0/v1"
        ),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        telegram_marketing_channel_id=os.environ.get("TELEGRAM_MARKETING_CHANNEL_ID", ""),
        facebook_page_id=os.environ.get("FACEBOOK_PAGE_ID", ""),
        facebook_page_access_token=os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", ""),
        instagram_business_account_id=os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID", ""),
        min_margin=_float(os.environ.get("MIN_MARGIN"), 0.25),
        dry_run=_bool(os.environ.get("DRY_RUN"), True),
        database_path=os.environ.get("DATABASE_PATH", "./nexus_commerce.db"),
        hourly_interval_minutes=int(os.environ.get("HOURLY_INTERVAL_MINUTES", "60")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
