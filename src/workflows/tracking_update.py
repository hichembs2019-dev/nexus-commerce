"""Hourly job step 2 (spec): "تحديث أرقام التتبع" - propose reflecting CJ's
shipment tracking number back onto the matching Shopify order. Treated as a
gated, consensus+Telegram action like every other Shopify write (spec SS4
#3's examples are not exhaustive - "أي فعل له أثر خارجي" covers this too),
not auto-applied.
"""
from __future__ import annotations

import sqlite3

from ..agents.agent import Agent
from ..config import Settings
from ..db import repository
from ..db.models import ActionType, Proposal
from ..integrations.cj_client import CJClient
from .pipeline import submit_proposal


def update_tracking_numbers(
    conn: sqlite3.Connection, cj: CJClient, settings: Settings, agents: list[Agent]
) -> list[Proposal]:
    proposals: list[Proposal] = []

    for order_row in repository.get_orders_with_cj_order(conn):
        tracking = cj.track_shipment(order_row["cj_order_id"])
        if not tracking.tracking_number:
            continue  # CJ has no tracking number yet - nothing to propose
        if order_row["tracking_number"] == tracking.tracking_number:
            continue  # already reflected, nothing changed

        payload = {
            "order_id": order_row["shopify_order_id"],
            "tracking_number": tracking.tracking_number,
            "carrier": tracking.carrier,
        }
        proposal = submit_proposal(
            conn,
            action_type=ActionType.UPDATE_TRACKING.value,
            payload=payload,
            justification=f"CJ reports tracking {tracking.tracking_number} for order {order_row['shopify_order_id']}",
            cost=0,
            risk="low",
            proposed_by="system:tracking_update",
            settings=settings,
            agents=agents,
        )
        proposals.append(proposal)

    return proposals
