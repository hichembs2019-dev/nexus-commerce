"""Spec's main loop: hourly (orders, tracking, price/inventory) + daily (new
products). Each job function takes an App and does one pass - APScheduler
itself (wired in main.py) is what decides timing; this module stays
testable without a real scheduler by calling these functions directly.
"""
from __future__ import annotations

import logging

from .app import App
from .workflows.new_product_discovery import discover_new_products
from .workflows.order_fulfillment import check_new_paid_orders
from .workflows.price_inventory_review import review_prices_and_inventory
from .workflows.tracking_update import update_tracking_numbers

logger = logging.getLogger("nexus_commerce.scheduler")

# Owner's explicit instruction, 2026-10-19 ("قلت لك كل المنتوجات مادام
# فيها ارباح" - I told you ALL products as long as they're profitable):
# the three fixed niche categories this used to carry were never what was
# asked for and were quietly narrowing every search to a handful of
# products - "" is CJ's own documented "no keyword" browse-everything
# query (see CJClient.search_products()'s own docstring), so every real
# candidate CJ offers is considered, filtered only by the real margin
# check in discover_new_products() - never by category.
DEFAULT_DISCOVERY_QUERIES = [""]


def run_hourly(app: App) -> dict:
    """Spec's hourly steps 1-3: paid orders -> CJ proposals, tracking
    updates, price/inventory review. Each step's own failure is caught and
    logged rather than aborting the remaining steps - one bad Shopify/CJ
    response must not skip the other two checks for the hour.
    """
    results = {}
    for name, fn in (
        ("new_paid_orders", lambda: check_new_paid_orders(app.conn, app.shopify, app.settings, app.agents)),
        ("tracking_updates", lambda: update_tracking_numbers(app.conn, app.cj, app.settings, app.agents)),
        (
            "price_inventory_review",
            lambda: review_prices_and_inventory(app.conn, app.shopify, app.cj, app.settings, app.agents),
        ),
    ):
        try:
            proposals = fn()
            results[name] = len(proposals)
            for proposal in proposals:
                _execute_if_consensus_reached(app, proposal)
        except Exception:  # noqa: BLE001 - one step's failure must not skip the rest
            logger.exception("hourly job step %s failed", name)
            results[name] = "error"
    return results


def run_daily(app: App, search_queries: list[str] | None = None) -> dict:
    """Spec's daily step: propose new products."""
    try:
        proposals = discover_new_products(
            app.conn,
            app.suppliers,
            app.web_search,
            app.settings,
            app.agents,
            search_queries or DEFAULT_DISCOVERY_QUERIES,
        )
        for proposal in proposals:
            _execute_if_consensus_reached(app, proposal)
        return {"new_product_discovery": len(proposals)}
    except Exception:  # noqa: BLE001
        logger.exception("daily job failed")
        return {"new_product_discovery": "error"}


def _execute_if_consensus_reached(app: App, proposal) -> None:
    """Owner's explicit instruction, 2026-10-14: full autonomy, no approval
    gate for anything, including the real sale - a CONSENSUS_REACHED
    proposal executes immediately. See workflows/pipeline.py's
    execute_autonomously() and its module docstring for the full rationale
    and what Telegram is still used for (a post-sale notification only).
    """
    from .db.models import ProposalStatus
    from .workflows.pipeline import execute_autonomously

    if proposal.status == ProposalStatus.CONSENSUS_REACHED.value:
        execute_autonomously(
            app.conn, proposal, app.executor, app.agents, app.telegram, app.marketing, app.marketing_reasoning_client
        )
    # FAILED_CONSENSUS / AUTO_REJECTED proposals are already fully logged by
    # submit_proposal() itself - nothing further to do with them here.


def execute_stuck_consensus_reached_proposals(app: App, limit: int | None = None) -> int:
    """Found live 2026-10-14: a real agreed-upon proposal (#25) reached
    CONSENSUS_REACHED, but the process was restarted (deploying an urgent
    fix) before run_daily()'s own `for proposal in proposals:` loop - which
    only ever sees proposals it JUST created in that same call - got to
    act on it. Nothing else in this codebase ever revisits an older
    CONSENSUS_REACHED row, so it would have sat there forever, silently.
    Call this once at startup so a restart can never again strand a real
    decision the agents already agreed on. Renamed from
    resend_stuck_consensus_reached_proposals now that reaching consensus
    means executing immediately, not sending to Telegram for approval.

    `limit`: found live 2026-10-18 on GitHub Actions (runs 39158203166 and
    39159056431) - each real execution now ends with a real
    post_execution_review() reasoning call that can take ~50-100 real
    seconds on the free Gemini tier (Groq is 429'd account-wide). A run
    that itself got cancelled mid-sweep leaves its own leftovers stuck for
    the NEXT run to catch up on, so an unbounded sweep here compounds:
    every cancelled run adds to a backlog the next run tries to clear in
    one unbounded, un-timeboxed loop, and both real runs this looked at
    were killed by the job's own timeout before finishing the sweep -
    before run_hourly() ever even started. A `limit` makes every firing
    do bounded, guaranteed real work and drain an arbitrarily large
    backlog over several 10-minute firings instead of trying (and
    failing) to clear it atomically in one. `None` keeps every existing
    caller's behavior (main.py's long-running daemon has no wall-clock
    deadline to protect) unbounded, unchanged.
    """
    from .db import repository
    from .db.models import ProposalStatus

    stuck = repository.get_proposals_by_status(app.conn, ProposalStatus.CONSENSUS_REACHED.value)
    if limit is not None:
        stuck = stuck[:limit]
    for proposal in stuck:
        _execute_if_consensus_reached(app, proposal)
    return len(stuck)
