"""Receiving the Approve/Reject button press. The parsing logic is pure and
fully unit-tested; the actual long-polling wiring (`build_application`) uses
python-telegram-bot's verified Application/CallbackQueryHandler shape (see
docs/SOURCES.md) but is real-integration-only - not meaningfully unit
testable without a live bot, so it is kept to the thinnest possible wrapper
around the tested parsing function and an injected decision callback.
"""
from __future__ import annotations

from typing import Callable

ALLOWED_DECISIONS = ("approve", "reject")


def parse_callback_data(data: str) -> tuple[str, int]:
    """"approve:123" -> ("approve", 123). Raises ValueError on anything that
    doesn't match exactly that shape, rather than guessing - a malformed or
    unexpected callback must never be silently treated as a decision.
    """
    action, sep, proposal_id_str = data.partition(":")
    if not sep or action not in ALLOWED_DECISIONS or not proposal_id_str.isdigit():
        raise ValueError(f"unrecognized callback_data: {data!r}")
    return action, int(proposal_id_str)


def build_application(bot_token: str, on_decision: Callable[[str, int], None]):
    """on_decision(action, proposal_id) is called for every valid button
    press. Not covered by the automated test suite - it needs a real bot
    token and a live Telegram connection; see README.md's manual
    verification step.
    """
    from telegram import Update
    from telegram.ext import Application, CallbackQueryHandler, ContextTypes

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        try:
            action, proposal_id = parse_callback_data(query.data)
        except ValueError:
            return
        on_decision(action, proposal_id)
        await query.edit_message_text(text=f"{query.message.text}\n\n→ {action}")

    application = Application.builder().token(bot_token).build()
    application.add_handler(CallbackQueryHandler(_handle))
    return application
