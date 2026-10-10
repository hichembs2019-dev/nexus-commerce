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

# Spec gives no fixed product-research query list (that is what the
# web-search/CJ-search tools are for, not a hardcoded niche) - a small
# starter list, meant to be replaced with the owner's actual product
# strategy once this runs for real.
DEFAULT_DISCOVERY_QUERIES = ["phone accessories", "kitchen gadgets", "pet accessories"]


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
                _send_if_consensus_reached(app, proposal)
        except Exception:  # noqa: BLE001 - one step's failure must not skip the rest
            logger.exception("hourly job step %s failed", name)
            results[name] = "error"
    return results


def run_daily(app: App, search_queries: list[str] | None = None) -> dict:
    """Spec's daily step: propose new products."""
    try:
        proposals = discover_new_products(
            app.conn, app.cj, app.web_search, app.settings, app.agents, search_queries or DEFAULT_DISCOVERY_QUERIES
        )
        for proposal in proposals:
            _send_if_consensus_reached(app, proposal)
        return {"new_product_discovery": len(proposals)}
    except Exception:  # noqa: BLE001
        logger.exception("daily job failed")
        return {"new_product_discovery": "error"}


def _send_if_consensus_reached(app: App, proposal) -> None:
    from .db.models import ProposalStatus
    from .workflows.pipeline import send_for_telegram_approval

    if proposal.status == ProposalStatus.CONSENSUS_REACHED.value:
        send_for_telegram_approval(app.conn, proposal, app.telegram)
    # FAILED_CONSENSUS / AUTO_REJECTED proposals are already fully logged by
    # submit_proposal() itself - nothing further to do with them here.
