from __future__ import annotations

import pytest

from src.integrations.marketing_client import (
    MarketingRegistry,
    MockMarketingClient,
    RealFacebookPageClient,
    RealInstagramClient,
)


class _FakeResponse:
    def __init__(self, status_code: int = 200, json_data: dict | None = None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


# --- RealFacebookPageClient ---


def test_facebook_post_sends_the_real_feed_endpoint_and_returns_the_post_id(monkeypatch):
    captured = {}

    def fake_post(url, *, data, timeout):
        captured["url"] = url
        captured["data"] = data
        return _FakeResponse(200, {"id": "123_456"})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    client = RealFacebookPageClient("123", "real-page-token")
    post_id = client.post("check out our new product!", link="https://example.com/p")

    assert post_id == "123_456"
    assert captured["url"] == "https://graph.facebook.com/v25.0/123/feed"
    assert captured["data"]["message"] == "check out our new product!"
    assert captured["data"]["link"] == "https://example.com/p"
    assert captured["data"]["access_token"] == "real-page-token"


def test_facebook_post_without_a_link_omits_the_link_field(monkeypatch):
    captured = {}

    def fake_post(url, *, data, timeout):
        captured["data"] = data
        return _FakeResponse(200, {"id": "1"})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    RealFacebookPageClient("123", "token").post("hello")

    assert "link" not in captured["data"]


def test_facebook_post_raises_on_a_non_200_or_missing_id(monkeypatch):
    def fake_post(url, *, data, timeout):
        return _FakeResponse(400, {"error": {"message": "Invalid OAuth access token"}})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(RuntimeError, match="Facebook Page post failed"):
        RealFacebookPageClient("123", "bad-token").post("hello")


# --- RealInstagramClient ---


def test_instagram_post_does_the_real_two_step_container_then_publish(monkeypatch):
    calls = []

    def fake_post(url, *, data, timeout):
        calls.append((url, data))
        if url.endswith("/media"):
            return _FakeResponse(200, {"id": "container-1"})
        if url.endswith("/media_publish"):
            return _FakeResponse(200, {"id": "media-1"})
        raise AssertionError(f"unexpected url {url}")

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    client = RealInstagramClient("ig-user-1", "token")
    media_id = client.post("new arrival!", image_url="https://example.com/img.jpg")

    assert media_id == "media-1"
    assert calls[0][0] == "https://graph.facebook.com/v25.0/ig-user-1/media"
    assert calls[0][1]["image_url"] == "https://example.com/img.jpg"
    assert calls[0][1]["caption"] == "new arrival!"
    assert calls[1][0] == "https://graph.facebook.com/v25.0/ig-user-1/media_publish"
    assert calls[1][1]["creation_id"] == "container-1"


def test_instagram_post_without_an_image_raises_rather_than_silently_posting_nothing():
    client = RealInstagramClient("ig-user-1", "token")

    with pytest.raises(ValueError, match="requires image_url"):
        client.post("text only, no image")


def test_instagram_post_raises_if_container_creation_fails(monkeypatch):
    def fake_post(url, *, data, timeout):
        return _FakeResponse(400, {"error": {"message": "bad image url"}})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(RuntimeError, match="container creation failed"):
        RealInstagramClient("ig-user-1", "token").post("x", image_url="https://example.com/bad.jpg")


def test_instagram_post_raises_if_publish_step_fails(monkeypatch):
    def fake_post(url, *, data, timeout):
        if url.endswith("/media"):
            return _FakeResponse(200, {"id": "container-1"})
        return _FakeResponse(400, {"error": {"message": "expired container"}})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(RuntimeError, match="publish failed"):
        RealInstagramClient("ig-user-1", "token").post("x", image_url="https://example.com/img.jpg")


# --- RealTelegramChannelClient ---
#
# No direct unit test here, matching this project's existing convention:
# RealTelegramClient (integrations/telegram_client.py) has none either.
# Found live while writing these tests - `import telegram` itself panics
# in this sandbox (`cryptography`'s Rust/cffi bindings:
# "ModuleNotFoundError: No module named '_cffi_backend'" ->
# pyo3_runtime.PanicException), independent of anything in this file. The
# real send_photo/send_message call shapes are still documented in
# RealTelegramChannelClient's own docstring/code, consistent with the
# already-verified send_message shape in telegram_client.py.


# --- MockMarketingClient / MarketingRegistry ---


def test_mock_marketing_client_records_every_post():
    client = MockMarketingClient()

    client.post("hello", image_url="https://x/img.jpg", link="https://x/p")

    assert client.posts == [{"text": "hello", "image_url": "https://x/img.jpg", "link": "https://x/p"}]


def test_registry_posts_to_every_platform_independently():
    telegram = MockMarketingClient()
    facebook = MockMarketingClient()
    registry = MarketingRegistry({"telegram": telegram, "facebook": facebook})

    results = registry.post_to_all("new product!", image_url="https://x/img.jpg")

    assert results["telegram"]["success"] is True
    assert results["facebook"]["success"] is True
    assert len(telegram.posts) == 1
    assert len(facebook.posts) == 1


def test_registry_one_platform_failing_does_not_stop_the_others():
    class _FailingClient:
        def post(self, text, *, image_url=None, link=None):
            raise RuntimeError("boom")

    working = MockMarketingClient()
    registry = MarketingRegistry({"broken": _FailingClient(), "telegram": working})

    results = registry.post_to_all("x")

    assert results["broken"]["success"] is False
    assert "boom" in results["broken"]["error"]
    assert results["telegram"]["success"] is True
    assert len(working.posts) == 1


def test_empty_registry_has_zero_platforms():
    registry = MarketingRegistry({})

    assert len(registry) == 0
    assert registry.names == []
