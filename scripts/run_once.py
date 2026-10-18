"""One real pass of the hourly jobs, then exit - for a scheduler that
fires a fresh process each time (GitHub Actions `schedule`, see
.github/workflows/run_hourly.yml) instead of staying up as a daemon
(src/main.py, for a real always-on server). Same startup sweep and same
real job functions as main.py - the only thing missing here is the
Telegram long-poll listener, which only matters for a legacy
awaiting_telegram tap (see pipeline.py's own docstring) and is not
needed for a process that is about to exit anyway.
"""
from __future__ import annotations

import logging

from src.app import build_app
from src.config import load_settings
from src.scheduler import execute_stuck_consensus_reached_proposals, run_daily, run_hourly
from src.workflows.pipeline import execute_stuck_awaiting_telegram_proposals


def main() -> None:
    settings = load_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    logger = logging.getLogger("nexus_commerce.run_once")

    app = build_app(settings)

    # Found live 2026-10-18 (GitHub Actions runs 39158203166, 39159056431):
    # an unbounded sweep here, with real post_execution_review() calls
    # costing ~50-100s each on the free Gemini tier, was killed by the
    # job's own timeout before finishing - and a run killed mid-sweep
    # leaves its own leftovers for the next run, compounding the backlog.
    # This process exits right after one pass (unlike main.py's daemon),
    # so a bounded limit lets every 10-minute firing make guaranteed
    # progress and drain any backlog over several firings instead of
    # risking the same timeout kill every single time. 5 * ~100s worst
    # case = ~500s, leaving real headroom in the 20-minute job budget for
    # run_hourly()'s own steps afterward.
    STUCK_PROPOSAL_LIMIT_PER_RUN = 5
    resumed = execute_stuck_consensus_reached_proposals(app, limit=STUCK_PROPOSAL_LIMIT_PER_RUN)
    if resumed:
        logger.warning("executed %d proposal(s) stuck at consensus_reached from before this run", resumed)

    caught_up = execute_stuck_awaiting_telegram_proposals(app.conn, app.executor, app.agents, app.telegram, app.marketing)
    if caught_up:
        logger.warning("executed %d proposal(s) stuck at awaiting_telegram", caught_up)

    hourly_result = run_hourly(app)
    logger.info("run_hourly: %s", hourly_result)

    import os

    if os.environ.get("RUN_DAILY_TOO") == "1":
        daily_result = run_daily(app)
        logger.info("run_daily: %s", daily_result)


if __name__ == "__main__":
    main()
