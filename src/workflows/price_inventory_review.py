"""Hourly job step 3 (spec): "مراجعة الأسعار والمخزون عند المورّد" - compare
each listed product's CJ supplier price against what Shopify currently
charges, and propose a price update if the supplier's price moved enough
that the margin would otherwise drift. Products with no linked CJ product
(cj_product_id empty - not dropshipped, or not yet linked) are skipped, not
treated as an error.
"""
from __future__ import annotations

import sqlite3

from ..agents.agent import Agent
from ..config import Settings
from ..db.models import ActionType, Proposal
from ..integrations.cj_client import CJClient
from ..integrations.shopify_client import ShopifyClient
from ..tools.profit_calculator import CostBreakdown, margin
from .pipeline import submit_proposal

# Spec gives no exact trigger threshold for "the supplier price changed
# enough to matter" - 1 cent of CJ price drift would not be worth a
# consensus round and a Telegram ping every hour. 5% is a documented,
# deliberately simple choice, not a verified business requirement.
PRICE_CHANGE_THRESHOLD = 0.05


def review_prices_and_inventory(
    conn: sqlite3.Connection,
    shopify: ShopifyClient,
    cj: CJClient,
    settings: Settings,
    agents: list[Agent],
) -> list[Proposal]:
    proposals: list[Proposal] = []

    for product in shopify.get_products():
        if not product.cj_product_id:
            continue

        try:
            cj_product = cj.get_product(product.cj_product_id)
        except (KeyError, NotImplementedError):
            continue

        if cj_product.price <= 0:
            continue

        change = abs(product.price - cj_product.price) / cj_product.price
        if change < PRICE_CHANGE_THRESHOLD:
            continue

        # A simple, documented repricing rule. The obvious-looking
        # alternative - "keep the same absolute markup the current listing
        # implies", i.e. cj_product.price + (product.price - cj_product.price)
        # - always reduces algebraically to product.price, a no-op that can
        # never actually change the price no matter how far the supplier's
        # cost has moved, because ShopifyProduct carries no record of what
        # the supplier price was when the listing was last set. With no
        # history to anchor an "old markup" to, this reprices to exactly
        # MIN_MARGIN over the new supplier cost instead - a real floor the
        # project already has a verified number for, not a guessed business
        # rule.
        suggested_price = round(cj_product.price / (1 - settings.min_margin), 2)

        breakdown = CostBreakdown(
            sale_price=suggested_price,
            product_cost=cj_product.price,
            shipping_cost=0,
            shopify_fee=0,
            payment_processing_fee=0,
        )

        proposal = submit_proposal(
            conn,
            action_type=ActionType.UPDATE_PRICE.value,
            payload={
                "product_id": product.product_id,
                "new_price": suggested_price,
                "cost_breakdown": vars(breakdown),
            },
            justification=(
                f"CJ price for {product.cj_product_id} moved to {cj_product.price} "
                f"({change:.1%} change) - current Shopify price {product.price}"
            ),
            cost=0,
            risk="low",
            proposed_by="system:price_inventory_review",
            settings=settings,
            agents=agents,
        )
        proposals.append(proposal)

    return proposals
