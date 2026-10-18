"""Promotes a product just published to Shopify on every configured real
marketing platform - see integrations/marketing_client.py for which
platforms and why. Triggered right after a real PUBLISH_PRODUCT
execution (pipeline.py), not gated by any agent vote: a marketing post
spends no money and reverses trivially (delete the post), so it follows
the owner's "work, not approve/reject" instruction (2026-10-18) by
default, the same way the single agent's own proposals do.
"""
from __future__ import annotations

from ..integrations.anthropic_client import AgentReasoningClient
from ..integrations.marketing_client import MarketingRegistry

_COPY_SYSTEM_PROMPT = """You are a social media copywriter for an online store. Write one short, \
appealing post promoting the product described to you - the kind of caption that makes someone \
stop scrolling and tap through. 1-3 sentences, no hashtags spam (at most 2-3 relevant ones), no \
markdown, no quotation marks around the whole thing. Output ONLY the post text, nothing else - no \
preamble, no explanation."""


def generate_post_copy(reasoning_client: AgentReasoningClient, title: str, description: str, price: float) -> str:
    user_prompt = f"Product: {title}\nDescription: {description}\nPrice: ${price}"
    return reasoning_client.complete(_COPY_SYSTEM_PROMPT, user_prompt).strip()


def promote_published_product(
    registry: MarketingRegistry,
    reasoning_client: AgentReasoningClient,
    *,
    title: str,
    description: str,
    price: float,
    image_url: str | None,
    product_url: str | None,
) -> dict[str, dict]:
    """Returns {} if no platform is configured (nothing to do, not an
    error - see app.py for how an empty registry is handled)."""
    if len(registry) == 0:
        return {}

    copy = generate_post_copy(reasoning_client, title, description, price)
    return registry.post_to_all(copy, image_url=image_url, link=product_url)
