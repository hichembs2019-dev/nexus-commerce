"""Long-running service entrypoint - `python -m src.main` (also the
Docker CMD). Starts the hourly/daily APScheduler jobs in the background and
blocks on the Telegram listener (or, with no bot token configured, just
sleeps - proposals still reach AWAITING_TELEGRAM and wait there for whenever
a token is added).
"""
from __future__ import annotations

import logging
import time

from apscheduler.schedulers.background import BackgroundScheduler

from .app import build_app
from .config import load_settings
from .scheduler import run_daily, run_hourly
from .workflows.pipeline import handle_telegram_decision


def main() -> None:
    settings = load_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    logger = logging.getLogger("nexus_commerce.main")

    app = build_app(settings)

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        lambda: run_hourly(app), "interval", minutes=settings.hourly_interval_minutes, id="hourly"
    )
    scheduler.add_job(lambda: run_daily(app), "cron", hour=0, minute=0, id="daily")
    scheduler.start()
    logger.info("nexus-commerce started (DRY_RUN=%s, hourly every %s min)", settings.dry_run, settings.hourly_interval_minutes)

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
            "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set - approvals cannot be received; "
            "proposals will reach awaiting_telegram and sit there until configured."
        )
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            scheduler.shutdown()


if __name__ == "__main__":
    main()
