"""Daily job (spec, widened by the owner's own later instruction): "اقتراح
منتجات جديدة" - search *every registered supplier's* catalog (not just CJ -
"الوكلاء... ليسوا محددين مع من يشتغلون"), do a little competitor research via
the web-search tool, and propose publishing whichever candidate clears
MIN_MARGIN with the best profit, from whichever supplier offers it. Every
proposal still goes through submit_proposal() (limits -> 5-agent consensus)
like everything else; this module only finds candidates and estimates a sale
price for each.

Widening the SEARCH to every supplier is safe - it is read-only. It does not
widen who actually gets PAID: a proposal sourced from a supplier whose client
is still an honest NotImplementedError stub (see docs/UNVERIFIED.md) is still
proposed and still goes through consensus + Telegram like any other, but its
own execution will raise that same documented error rather than guessing an
unverified API - exactly the discipline CJ's own RealCJClient already follows.
"""
from __future__ import annotations

import sqlite3

from ..agents.agent import Agent
from ..config import Settings
from ..db.models import ActionType, Proposal
from ..integrations.supplier_client import SupplierRegistry
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
    suppliers: SupplierRegistry,
    web_search: WebSearchTool,
    settings: Settings,
    agents: list[Agent],
    search_queries: list[str],
) -> list[Proposal]:
    proposals: list[Proposal] = []

    for query in search_queries:
        for supplier_name, candidate in suppliers.search_all(query):
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

            # Competitor research is informational only - counted in the
            # justification text, never read by the margin/price decision
            # above. A search failure (e.g. the provider's own account
            # issue, found live 2026-10-13) must not block a real,
            # already-profitable proposal from reaching the agents.
            try:
                competitor_research = web_search.search(f"{candidate.title} price")
            except Exception:  # noqa: BLE001 - see comment above
                competitor_research = []

            proposal = submit_proposal(
                conn,
                action_type=ActionType.PUBLISH_PRODUCT.value,
                payload={
                    "title": candidate.title,
                    "description": f"{candidate.title} - من مورّد {supplier_name}",
                    "price": sale_price,
                    "images": [],
                    "supplier": supplier_name,
                    "cj_product_id": candidate.product_id,
                    "cost_breakdown": vars(breakdown),
                },
                justification=(
                    f"found via {supplier_name} search '{query}'; {len(competitor_research)} "
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
