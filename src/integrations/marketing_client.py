"""Real social posting for a published product - owner's explicit
instruction, 2026-10-18 ("ابحث انت و قرر الافضل" - research it and
decide the best): a store full of real products with no one seeing them
sells nothing (owner's own point, same conversation: "الزبائن تدخل
المتجر ان وجد" - customers enter the store if it exists/is visible).
This module is the "make it visible" half; it does not generate traffic
by itself, only posts real content to platforms that already have a real
audience.

Three platforms chosen after checking real, current cost/access, not
assumed - see docs/SOURCES.md "Marketing - real platform research":
- Telegram: already free (same bot token as the rest of this project),
  posts to a separate public channel, not the owner's private approval
  chat.
- Facebook Page feed: free Graph API call, confirmed (Meta's own docs,
  2026-06) that posting to a Page YOU own/manage needs only Standard
  Access - no lengthy App Review, unlike a third-party Tech Provider app.
- Instagram (same Meta Business account): free Graph API, two-step
  publish (create a media container, then publish it) - confirmed from
  Meta's own Instagram Platform docs.
X/Twitter is deliberately NOT here: as of 2026 it is pay-per-use
(roughly $0.01-$0.20 per post depending on content), which contradicts
the owner's explicit "free only" instruction - see docs/SOURCES.md.
Pinterest is deliberately NOT here either: its API is free, but public
posting needs Pinterest's own manual "Standard access" review, which can
sit pending for weeks with no owner-side lever to speed it up - nothing
to build until that approval exists for real.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class MarketingClient(ABC):
    @abstractmethod
    def post(self, text: str, *, image_url: str | None = None, link: str | None = None) -> str:
        """Publishes one real post. Returns the platform's own id for it
        (usable to build a real URL back to the post). Raises on a
        non-success response - never silently drops a failed post."""


class RealTelegramChannelClient(MarketingClient):
    """Same bot token as the rest of the project (see telegram_client.py)
    but a DIFFERENT chat_id - a public channel the bot is an admin of,
    not the owner's private approval chat. python-telegram-bot's real
    Bot.send_message/send_photo, same library already verified live for
    this project (docs/SOURCES.md "Telegram").
    """

    def __init__(self, bot_token: str, channel_id: str):
        self._bot_token = bot_token
        self._channel_id = channel_id

    def post(self, text: str, *, image_url: str | None = None, link: str | None = None) -> str:
        import asyncio

        from telegram import Bot

        full_text = f"{text}\n\n{link}" if link else text

        async def _send() -> str:
            bot = Bot(token=self._bot_token)
            if image_url:
                message = await bot.send_photo(chat_id=self._channel_id, photo=image_url, caption=full_text)
            else:
                message = await bot.send_message(chat_id=self._channel_id, text=full_text)
            return str(message.message_id)

        return asyncio.run(_send())


class RealFacebookPageClient(MarketingClient):
    """Meta Graph API, Page feed - verified against developers.facebook.com
    "Pages API > Posts" (2026-10-18, see docs/SOURCES.md): POST
    https://graph.facebook.com/<version>/<page_id>/feed with {"message", "link"?}
    and the Page access token, returns {"id": "<page_post_id>"}. A Page
    the owner manages themselves needs only Standard Access for this -
    no App Review wait (Meta's own docs, same source).
    """

    _API_VERSION = "v25.0"

    def __init__(self, page_id: str, access_token: str):
        self._page_id = page_id
        self._access_token = access_token

    def post(self, text: str, *, image_url: str | None = None, link: str | None = None) -> str:
        import httpx

        body: dict = {"message": text, "access_token": self._access_token}
        if link:
            body["link"] = link

        response = httpx.post(
            f"https://graph.facebook.com/{self._API_VERSION}/{self._page_id}/feed", data=body, timeout=30
        )
        payload = response.json()
        if response.status_code != 200 or "id" not in payload:
            raise RuntimeError(f"Facebook Page post failed ({response.status_code}): {payload}")
        return payload["id"]


class RealInstagramClient(MarketingClient):
    """Meta Graph API, Instagram content publishing - verified against
    developers.facebook.com "Instagram Platform > Content Publishing"
    (2026-10-18, see docs/SOURCES.md): a two-step real flow - POST
    .../<ig_user_id>/media with {"image_url", "caption"} returns a real
    container id, then POST .../<ig_user_id>/media_publish with
    {"creation_id"} returns the real published media id. Image-only
    (Instagram's own real constraint: a caption with no image is not a
    publishable post on this endpoint) - raises clearly rather than
    silently dropping the caption-only case.
    """

    _API_VERSION = "v25.0"

    def __init__(self, ig_user_id: str, access_token: str):
        self._ig_user_id = ig_user_id
        self._access_token = access_token

    def post(self, text: str, *, image_url: str | None = None, link: str | None = None) -> str:
        import httpx

        if not image_url:
            raise ValueError("Instagram requires image_url - a caption-only post is not supported by this endpoint")

        full_caption = f"{text}\n\n{link}" if link else text
        base = f"https://graph.facebook.com/{self._API_VERSION}/{self._ig_user_id}"

        container_resp = httpx.post(
            f"{base}/media",
            data={"image_url": image_url, "caption": full_caption, "access_token": self._access_token},
            timeout=30,
        )
        container_payload = container_resp.json()
        if container_resp.status_code != 200 or "id" not in container_payload:
            raise RuntimeError(f"Instagram media container creation failed ({container_resp.status_code}): {container_payload}")

        publish_resp = httpx.post(
            f"{base}/media_publish",
            data={"creation_id": container_payload["id"], "access_token": self._access_token},
            timeout=30,
        )
        publish_payload = publish_resp.json()
        if publish_resp.status_code != 200 or "id" not in publish_payload:
            raise RuntimeError(f"Instagram media publish failed ({publish_resp.status_code}): {publish_payload}")
        return publish_payload["id"]


class MockMarketingClient(MarketingClient):
    """Records every post in memory - lets a test drive the whole
    promote_published_product() flow without any real account."""

    def __init__(self):
        self.posts: list[dict] = []
        self._next_id = 0

    def post(self, text: str, *, image_url: str | None = None, link: str | None = None) -> str:
        self._next_id += 1
        self.posts.append({"text": text, "image_url": image_url, "link": link})
        return f"mock-post-{self._next_id}"


class MarketingRegistry:
    """Named platforms, each exposing the same MarketingClient-shaped
    interface - mirrors SupplierRegistry's own convention
    (integrations/supplier_client.py)."""

    def __init__(self, platforms: dict[str, MarketingClient]):
        self._platforms = dict(platforms)

    def post_to_all(self, text: str, *, image_url: str | None = None, link: str | None = None) -> dict[str, dict]:
        """Posts to every registered platform independently - one
        platform's failure (a bad token, a transient API error) must not
        stop the others from posting. Returns {platform_name: {"success":
        bool, "post_id": str | None, "error": str | None}}."""
        results: dict[str, dict] = {}
        for name, client in self._platforms.items():
            try:
                post_id = client.post(text, image_url=image_url, link=link)
                results[name] = {"success": True, "post_id": post_id, "error": None}
            except Exception as exc:  # noqa: BLE001 - one platform's failure must not skip the rest
                results[name] = {"success": False, "post_id": None, "error": str(exc)}
        return results

    @property
    def names(self) -> list[str]:
        return list(self._platforms.keys())

    def __len__(self) -> int:
        return len(self._platforms)
