"""Spec-mandated full DRY_RUN simulation, with mocks for every external API:
new product -> customer order -> payment -> order from supplier -> tracking.

Every step goes through the real pipeline (submit_proposal -> consensus ->
send_for_telegram_approval -> handle_telegram_decision -> execute ->
post-execution review), with all 5 agents approving so each step actually
reaches execution. DRY_RUN stays true throughout, so nothing real is ever
touched - only the audit trail and the mocks' in-memory state prove the
journey happened.
"""
from __future__ import annotations

from src.db import repository
from src.db.models import ProposalStatus
from src.integrations.cj_client import CJProduct, TrackingInfo
from src.integrations.shopify_client import ShopifyOrder
from src.workflows.new_product_discovery import discover_new_products
from src.workflows.order_fulfillment import check_new_paid_orders
from src.workflows.pipeline import handle_telegram_decision, send_for_telegram_approval
from src.workflows.tracking_update import update_tracking_numbers

from .conftest import all_approving_agents


def test_full_journey_new_product_to_paid_order_to_supplier_order_to_tracking(
    conn, settings, shopify, cj, telegram, web_search, executor
):
    agents = all_approving_agents()

    # 1. A new CJ product is discovered and clears MIN_MARGIN -> proposed for publishing.
    cj.catalog.append(CJProduct(product_id="CJ-1", title="Phone Case", price=5.0))
    discovery_proposals = discover_new_products(
        conn, cj, web_search, settings, agents=all_approving_agents(), search_queries=["phone"]
    )
    assert len(discovery_proposals) == 1
    publish_proposal = discovery_proposals[0]
    assert publish_proposal.status == ProposalStatus.CONSENSUS_REACHED.value

    publish_proposal = send_for_telegram_approval(conn, publish_proposal, telegram)
    assert publish_proposal.status == ProposalStatus.AWAITING_TELEGRAM.value

    decision = handle_telegram_decision(conn, publish_proposal.id, "approve", executor, all_approving_agents())
    assert decision.proposal.status == ProposalStatus.EXECUTED.value
    # DRY_RUN: no real product was ever created in Shopify.
    assert shopify.products == []
    assert decision.correction_proposal is None

    # Even though the publish was only simulated, this is a DRY_RUN rehearsal
    # of the whole journey - so a Shopify order for the (would-be) product is
    # now seeded directly to exercise the next steps.
    shopify.orders.append(
        ShopifyOrder(
            order_id="SHOP-1001",
            financial_status="paid",
            total_price=10.0,
            line_items=[{"cj_product_id": "CJ-1", "quantity": 1}],
            shipping_address={"country": "US"},
        )
    )

    # 2. The paid order is detected and proposed for ordering from CJ.
    order_proposals = check_new_paid_orders(conn, shopify, settings, agents=all_approving_agents())
    assert len(order_proposals) == 1
    cj_order_proposal = order_proposals[0]
    assert cj_order_proposal.status == ProposalStatus.CONSENSUS_REACHED.value
    assert repository.order_exists_for_shopify_order(conn, "SHOP-1001")

    cj_order_proposal = send_for_telegram_approval(conn, cj_order_proposal, telegram)
    decision = handle_telegram_decision(conn, cj_order_proposal.id, "approve", executor, all_approving_agents())
    assert decision.proposal.status == ProposalStatus.EXECUTED.value
    # DRY_RUN: no real CJ order was ever placed.
    assert cj.orders == {}

    # 3. Because DRY_RUN never produces a real cj_order_id, the orders row
    # has none - the tracking step has nothing to attach to yet, which is
    # the correct, honest behaviour: DRY_RUN proves the decision pipeline,
    # never a real fulfillment side effect.
    order_row = repository.get_order_by_proposal_id(conn, cj_order_proposal.id)
    assert order_row["cj_order_id"] is None
    assert update_tracking_numbers(conn, cj, settings, agents=all_approving_agents()) == []

    # To rehearse the tracking step itself, attach a real (mock) CJ order to
    # the same orders row as a dropshipping fulfillment would eventually do,
    # then let CJ report a tracking number for it.
    cj_order_id = cj.create_order(product_id="CJ-1", quantity=1, shipping_address={"country": "US"})
    repository.update_order_cj(conn, order_row["id"], cj_order_id, status="ordered")
    cj.set_tracking(cj_order_id, TrackingInfo(status="shipped", tracking_number="TRACK-999", carrier="DHL"))

    tracking_proposals = update_tracking_numbers(conn, cj, settings, agents=all_approving_agents())
    assert len(tracking_proposals) == 1
    tracking_proposal = tracking_proposals[0]
    assert tracking_proposal.payload == {
        "order_id": "SHOP-1001",
        "tracking_number": "TRACK-999",
        "carrier": "DHL",
    }

    tracking_proposal = send_for_telegram_approval(conn, tracking_proposal, telegram)
    decision = handle_telegram_decision(conn, tracking_proposal.id, "approve", executor, all_approving_agents())
    assert decision.proposal.status == ProposalStatus.EXECUTED.value
    # DRY_RUN: Shopify's own tracking field was never really updated.
    assert shopify.tracking_updates == []

    # _link_order_result() only writes back to the local orders row for a
    # real, successful (non-DRY_RUN) execution - see its own docstring in
    # pipeline.py. In DRY_RUN nothing really happened, so the local
    # bookkeeping deliberately stays untouched too; only the proposal's own
    # payload (asserted above) carries the simulated tracking number.
    final_order_row = repository.get_order_by_proposal_id(conn, cj_order_proposal.id)
    assert final_order_row["tracking_number"] is None

    # Full audit trail exists for every step of the journey.
    audit_actions = [row["action"] for row in conn.execute("SELECT action FROM audit_log ORDER BY id").fetchall()]
    assert audit_actions.count("executed") == 3
    assert "telegram_approved" in audit_actions


def test_a_rejected_telegram_decision_never_touches_any_external_mock(
    conn, settings, shopify, cj, telegram, web_search, executor
):
    cj.catalog.append(CJProduct(product_id="CJ-1", title="Pet Leash", price=4.0))

    proposals = discover_new_products(
        conn, cj, web_search, settings, agents=all_approving_agents(), search_queries=["pet"]
    )
    proposal = send_for_telegram_approval(conn, proposals[0], telegram)

    decision = handle_telegram_decision(conn, proposal.id, "reject", executor, all_approving_agents())

    assert decision.proposal.status == ProposalStatus.TELEGRAM_REJECTED.value
    assert decision.correction_proposal is None
    assert shopify.products == []
    assert telegram.sent == [(proposal.id, telegram.sent[0][1])]
