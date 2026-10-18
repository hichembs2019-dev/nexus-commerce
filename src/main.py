"""Long-running service entrypoint - `python -m src.main` (also the
Docker CMD). Starts the hourly/daily APScheduler jobs in the background and
blocks on the Telegram listener (or, with no bot token configured, just
sleeps).

Owner's explicit instruction, 2026-10-14: full autonomy, no approval gate for
anything - a CONSENSUS_REACHED proposal executes immediately (see
scheduler.py / workflows/pipeline.py). The Telegram listener below is kept
only so a real Approve/Reject tap on a message sent *before* this change
still works; nothing new is ever sent with buttons again.
"""
from __future__ import annotations

import logging
import time

from apscheduler.schedulers.background import BackgroundScheduler

from .app import build_app
from .config import load_settings
from .scheduler import execute_stuck_consensus_reached_proposals, run_daily, run_hourly
from .workflows.pipeline import execute_stuck_awaiting_telegram_proposals, handle_telegram_decision


def main() -> None:
    settings = load_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    logger = logging.getLogger("nexus_commerce.main")

    app = build_app(settings)

    # Found live 2026-10-14: a real proposal the agents already agreed on
    # (CONSENSUS_REACHED) never got acted on because the process was
    # restarted before it was executed - nothing else ever revisits it. Sweep
    # once at every startup so a restart can never strand a real decision.
    resumed = execute_stuck_consensus_reached_proposals(app)
    if resumed:
        logger.warning("executed %d proposal(s) stuck at consensus_reached from before this restart", resumed)

    # One-time catch-up for the full-autonomy policy change itself: any
    # proposal already sent to Telegram with real buttons that the owner
    # never tapped now executes instead of waiting forever for a tap that,
    # per the owner's own instruction, is never supposed to be required.
    caught_up = execute_stuck_awaiting_telegram_proposals(
        app.conn, app.executor, app.agents, app.telegram, app.marketing, app.marketing_reasoning_client
    )
    if caught_up:
        logger.warning("executed %d proposal(s) stuck at awaiting_telegram under the new full-autonomy policy", caught_up)

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        lambda: run_hourly(app), "interval", minutes=settings.hourly_interval_minutes, id="hourly"
    )
    # Owner's explicit instruction: everything on the same cadence as the
    # hourly jobs, not once a day at midnight. New-product discovery is
    # real API calls (CJ search + a full 5-agent consensus per candidate),
    # so at a 1-minute interval this will burn through a free reasoning
    # provider's quota fast - see docs/UNVERIFIED.md "Gemini free tier
    # reliability".
    scheduler.add_job(
        lambda: run_daily(app), "interval", minutes=settings.hourly_interval_minutes, id="daily"
    )
    scheduler.start()
    logger.info("nexus-commerce started (DRY_RUN=%s, everything every %s min)", settings.dry_run, settings.hourly_interval_minutes)

    def on_decision(action: str, proposal_id: int) -> None:
        try:
            handle_telegram_decision(app.conn, proposal_id, action, app.executor, app.agents)
        except Exception:
            logger.exception("failed to handle Telegram decision for proposal %s", proposal_id)

    if settings.telegram_configured:
        from .integrations.telegram_listener import build_application

        application = build_application(settings.telegram_bot_token, on_decision)
        logger.info("Telegram listener starting (long polling)")
        # bootstrap_retries=-1 verified directly from the installed library's
        # own docstring (telegram.ext.Application.run_polling): "< 0 - retry
        # indefinitely". The default is 0 (no retries) - a single failed
        # connection attempt at startup (DNS hiccup, Telegram momentarily
        # unreachable) would otherwise raise out of run_polling() uncaught,
        # crashing this whole process - including the BackgroundScheduler
        # already running in its own thread, which has nothing to do with
        # Telegram and has no reason to die with it. Found by actually
        # running this service, not assumed.
        application.run_polling(bootstrap_retries=-1)  # blocks - this is the process's "run forever"
    else:
        logger.warning(
            "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set - no post-sale notification can be sent "
            "and any legacy awaiting_telegram proposal cannot receive a tap, but every proposal still "
            "executes autonomously once it reaches consensus."
        )
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            scheduler.shutdown()


if __name__ == "__main__":
    main()
