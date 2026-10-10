"""Daily job (spec): "اقتراح منتجات جديدة" - search CJ's catalog, do a
little competitor research via the web-search tool, and propose publishing
anything that clears MIN_MARGIN. Every proposal still goes through
submit_proposal() (limits -> 5-agent consensus) like everything else; this
module only finds candidates and estimates a sale price for each.
"""
from __future__ import annotations

import sqlite3

from ..agents.agent import Agent
from ..config import Settings
from ..db.models import ActionType, Proposal
from ..integrations.cj_client import CJClient
from ..tools.profit_calculator import CostBreakdown, margin
from ..tools.web_search import WebSearchTool
from .pipeline import submit_proposal

# Spec names "دراسة المنتجات والمنافسين" (studying products and
# competitors) as a tool, not a pricing formula - this 2x-supplier-cost
# markup is a simple, documented starting point, not a verified business
# requirement. The actual decision still goes through MIN_MARGIN and the
# 5-agent consensus either way, so a bad guess here is caught downstream,
# not silently published.
MARKUP_MULTIPLIER = 2.0


def _suggest_sale_price(supplier_cost: float) -> float:
    return round(supplier_cost * MARKUP_MULTIPLIER, 2)


def discover_new_products(
    conn: sqlite3.Connection,
    cj: CJClient,
    web_search: WebSearchTool,
    settings: Settings,
    agents: list[Agent],
    search_queries: list[str],
) -> list[Proposal]:
    proposals: list[Proposal] = []

    for query in search_queries:
        for candidate in cj.search_products(query):
            if candidate.price <= 0:
                continue

            sale_price = _suggest_sale_price(candidate.price)
            breakdown = CostBreakdown(
                sale_price=sale_price,
                product_cost=candidate.price,
                shipping_cost=0,
                shopify_fee=0,
                payment_processing_fee=0,
            )
            if margin(breakdown) < settings.min_margin:
                continue  # not worth even proposing

            competitor_research = web_search.search(f"{candidate.title} price")

            proposal = submit_proposal(
                conn,
                action_type=ActionType.PUBLISH_PRODUCT.value,
                payload={
                    "title": candidate.title,
                    "description": f"{candidate.title} - من مورّد CJ Dropshipping",
                    "price": sale_price,
                    "images": [],
                    "cj_product_id": candidate.product_id,
                    "cost_breakdown": vars(breakdown),
                },
                justification=(
                    f"found via CJ search '{query}'; {len(competitor_research)} "
                    "competitor reference(s) found"
                ),
                cost=0,
                risk="medium",
                proposed_by="system:new_product_discovery",
                settings=settings,
                agents=agents,
            )
            proposals.append(proposal)

    return proposals
