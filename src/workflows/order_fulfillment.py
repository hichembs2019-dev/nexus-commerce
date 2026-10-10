"""Hourly job step 1 (spec): "فحص الطلبات المدفوعة الجديدة ثم مقترح طلبها
من CJ" - check newly-paid orders, propose ordering them from CJ. Every
proposal still goes through submit_proposal() (limits -> 5-agent consensus);
this module only decides WHICH orders are even candidates.
"""
from __future__ import annotations

import sqlite3

from ..agents.agent import Agent
from ..config import Settings
from ..db import repository
from ..db.models import ActionType, Proposal
from ..integrations.shopify_client import ShopifyClient
from ..tools.limits import check_payment_confirmed
from .pipeline import submit_proposal


def check_new_paid_orders(
    conn: sqlite3.Connection, shopify: ShopifyClient, settings: Settings, agents: list[Agent]
) -> list[Proposal]:
    proposals: list[Proposal] = []

    for order in shopify.get_recent_orders():
        if repository.order_exists_for_shopify_order(conn, order.order_id):
            continue  # already proposed (or already ordered) - never re-propose the same order

        payment_check = check_payment_confirmed(order.financial_status)
        if not payment_check.allowed:
            continue  # not paid yet - not an error, just not ready (spec SS4 #5)

        payload = {
            "shopify_order_id": order.order_id,
            "line_items": order.line_items,
            "shipping_address": order.shipping_address,
        }
        proposal = submit_proposal(
            conn,
            action_type=ActionType.CJ_ORDER.value,
            payload=payload,
            justification=f"Shopify order {order.order_id} is paid (financial_status=paid)",
            cost=order.total_price,
            risk="low" if order.total_price < 50 else "medium",
            proposed_by="system:order_fulfillment",
            settings=settings,
            agents=agents,
        )
        # Recorded as soon as we propose it (not only once executed) so a
        # second hourly run never proposes the same paid order twice while
        # the first proposal is still being negotiated/awaiting Telegram.
        repository.create_order(conn, proposal_id=proposal.id, shopify_order_id=order.order_id, cost=order.total_price)
        proposals.append(proposal)

    return proposals
