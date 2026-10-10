"""Sending the approval request. Verified usage: docs/SOURCES.md
"Telegram". See telegram_listener.py for receiving the button press back.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class TelegramClient(ABC):
    @abstractmethod
    def send_approval_request(self, proposal_id: int, summary: str) -> str:
        """Sends `summary` with Approve/Reject inline buttons whose
        callback_data is "approve:{proposal_id}" / "reject:{proposal_id}"
        (see telegram_listener.parse_callback_data). Returns the sent
        message's id.
        """


class RealTelegramClient(TelegramClient):
    def __init__(self, bot_token: str, chat_id: str):
        self._bot_token = bot_token
        self._chat_id = chat_id

    def send_approval_request(self, proposal_id: int, summary: str) -> str:
        import asyncio

        from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ موافق", callback_data=f"approve:{proposal_id}"),
                    InlineKeyboardButton("❌ رفض", callback_data=f"reject:{proposal_id}"),
                ]
            ]
        )

        async def _send() -> str:
            bot = Bot(token=self._bot_token)
            # NOTE: docs/UNVERIFIED.md "Telegram - proactive send_message" -
            # this exact call (chat_id=, text=, reply_markup=) was inferred,
            # not independently re-read from source. A wrong keyword fails
            # loudly here (TypeError), never silently.
            message = await bot.send_message(
                chat_id=self._chat_id, text=summary, reply_markup=keyboard
            )
            return str(message.message_id)

        return asyncio.run(_send())


class MockTelegramClient(TelegramClient):
    """Records every sent request in memory - what every test and every
    DRY_RUN run actually exercises.
    """

    def __init__(self):
        self.sent: list[tuple[int, str]] = []
        self._next_message_id = 1

    def send_approval_request(self, proposal_id: int, summary: str) -> str:
        self.sent.append((proposal_id, summary))
        message_id = str(self._next_message_id)
        self._next_message_id += 1
        return message_id
