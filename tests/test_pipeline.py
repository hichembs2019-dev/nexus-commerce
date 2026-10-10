from src.db import repository
from src.db.models import ActionType, ProposalStatus
from src.workflows.pipeline import (
    DecisionResult,
    handle_telegram_decision,
    send_for_telegram_approval,
    submit_proposal,
)

from .conftest import all_approving_agents


def test_submit_proposal_over_max_order_cost_is_auto_rejected_before_reaching_agents(conn, settings):
    settings.max_order_cost = 100.0
    agents = all_approving_agents()

    proposal = submit_proposal(
        conn,
        action_type=ActionType.CJ_ORDER.value,
        payload={"shopify_order_id": "1001"},
        justification="test",
        cost=150.0,
        risk="low",
        proposed_by="test",
        settings=settings,
        agents=agents,
    )

    assert proposal.status == ProposalStatus.AUTO_REJECTED.value
    # Never reached the agents at all.
    assert repository.get_votes_for_round(conn, proposal.id, 1) == []


def test_submit_proposal_within_limits_runs_full_consensus(conn, settings):
    agents = all_approving_agents()

    proposal = submit_proposal(
        conn,
        action_type=ActionType.CJ_ORDER.value,
        payload={"shopify_order_id": "1001"},
        justification="test",
        cost=50.0,
        risk="low",
        proposed_by="test",
        settings=settings,
        agents=agents,
    )

    assert proposal.status == ProposalStatus.CONSENSUS_REACHED.value
    assert len(repository.get_votes_for_round(conn, proposal.id, 1)) == 5


def test_submit_proposal_with_low_margin_cost_breakdown_is_auto_rejected(conn, settings):
    settings.min_margin = 0.5
    agents = all_approving_agents()

    proposal = submit_proposal(
        conn,
        action_type=ActionType.PUBLISH_PRODUCT.value,
        payload={
            "title": "x",
            "cost_breakdown": {
                "sale_price": 100,
                "product_cost": 90,
                "shipping_cost": 0,
                "shopify_fee": 0,
                "payment_processing_fee": 0,
            },
        },
        justification="test",
        cost=0,
        risk="low",
        proposed_by="test",
        settings=settings,
        agents=agents,
    )

    assert proposal.status == ProposalStatus.AUTO_REJECTED.value


def test_send_for_telegram_approval_requires_consensus_reached_first(conn, settings, telegram):
    agents = all_approving_agents()
    proposal = submit_proposal(
        conn,
        action_type=ActionType.CJ_ORDER.value,
        payload={},
        justification="t",
        cost=1000000.0,  # guaranteed over MAX_ORDER_COST -> auto_rejected
        risk="low",
        proposed_by="test",
        settings=settings,
        agents=agents,
    )
    assert proposal.status == ProposalStatus.AUTO_REJECTED.value

    try:
        send_for_telegram_approval(conn, proposal, telegram)
        assert False, "expected ValueError for a non-consensus-reached proposal"
    except ValueError:
        pass
    assert telegram.sent == []


def test_send_for_telegram_approval_sends_and_marks_awaiting(conn, settings, telegram):
    agents = all_approving_agents()
    proposal = submit_proposal(
        conn,
        action_type=ActionType.CJ_ORDER.value,
        payload={"shopify_order_id": "1001"},
        justification="t",
        cost=10,
        risk="low",
        proposed_by="test",
        settings=settings,
        agents=agents,
    )

    updated = send_for_telegram_approval(conn, proposal, telegram)

    assert updated.status == ProposalStatus.AWAITING_TELEGRAM.value
    assert len(telegram.sent) == 1
    assert telegram.sent[0][0] == proposal.id


def test_handle_telegram_decision_reject_does_not_execute(conn, settings, telegram, executor, shopify, cj):
    agents = all_approving_agents()
    proposal = submit_proposal(
        conn, action_type=ActionType.CJ_ORDER.value, payload={"product_id": "p1", "quantity": 1, "shipping_address": {}},
        justification="t", cost=10, risk="low", proposed_by="test", settings=settings, agents=agents,
    )
    send_for_telegram_approval(conn, proposal, telegram)

    result: DecisionResult = handle_telegram_decision(conn, proposal.id, "reject", executor, agents)

    assert result.proposal.status == ProposalStatus.TELEGRAM_REJECTED.value
    assert result.correction_proposal is None
    assert cj.orders == {}


def test_handle_telegram_decision_approve_executes_in_dry_run_without_real_side_effects(
    conn, settings, telegram, executor, shopify, cj
):
    assert settings.dry_run is True
    agents = all_approving_agents()
    proposal = submit_proposal(
        conn, action_type=ActionType.CJ_ORDER.value, payload={"product_id": "p1", "quantity": 1, "shipping_address": {}},
        justification="t", cost=10, risk="low", proposed_by="test", settings=settings, agents=agents,
    )
    send_for_telegram_approval(conn, proposal, telegram)

    result = handle_telegram_decision(conn, proposal.id, "approve", executor, agents)

    assert result.proposal.status == ProposalStatus.EXECUTED.value
    # DRY_RUN: nothing was actually ordered from CJ.
    assert cj.orders == {}


def test_handle_telegram_decision_rejects_a_proposal_not_awaiting_telegram(conn, settings, telegram, executor):
    agents = all_approving_agents()
    proposal = submit_proposal(
        conn, action_type=ActionType.CJ_ORDER.value, payload={}, justification="t", cost=10,
        risk="low", proposed_by="test", settings=settings, agents=agents,
    )
    # Never sent to Telegram - still at consensus_reached.
    try:
        handle_telegram_decision(conn, proposal.id, "approve", executor, agents)
        assert False, "expected ValueError"
    except ValueError:
        pass
