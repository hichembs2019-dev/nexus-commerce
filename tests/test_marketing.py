from __future__ import annotations

from src.integrations.anthropic_client import MockAgentReasoningClient
from src.integrations.marketing_client import MarketingRegistry, MockMarketingClient
from src.workflows.marketing import generate_post_copy, promote_published_product


def test_generate_post_copy_sends_the_product_details_and_returns_the_reply():
    reasoning = MockAgentReasoningClient(scripted_replies=["Grab this before it's gone! $19.99"])

    copy = generate_post_copy(reasoning, "Slim Wallet", "A slim magnetic wallet", 19.99)

    assert copy == "Grab this before it's gone! $19.99"
    system_prompt, user_prompt = reasoning.calls[0]
    assert "Slim Wallet" in user_prompt
    assert "19.99" in user_prompt
    assert "copywriter" in system_prompt.lower()


def test_promote_published_product_posts_generated_copy_to_every_platform():
    reasoning = MockAgentReasoningClient(scripted_replies=["Check out our new Slim Wallet!"])
    telegram = MockMarketingClient()
    facebook = MockMarketingClient()
    registry = MarketingRegistry({"telegram": telegram, "facebook": facebook})

    results = promote_published_product(
        registry, reasoning,
        title="Slim Wallet", description="A slim wallet", price=19.99,
        image_url="https://x/img.jpg", product_url=None,
    )

    assert results["telegram"]["success"] is True
    assert results["facebook"]["success"] is True
    assert telegram.posts[0]["text"] == "Check out our new Slim Wallet!"
    assert telegram.posts[0]["image_url"] == "https://x/img.jpg"


def test_promote_published_product_with_an_empty_registry_does_nothing_and_calls_no_reasoning():
    reasoning = MockAgentReasoningClient(scripted_replies=[])
    registry = MarketingRegistry({})

    results = promote_published_product(
        registry, reasoning,
        title="x", description="d", price=1.0, image_url=None, product_url=None,
    )

    assert results == {}
    assert reasoning.calls == []
