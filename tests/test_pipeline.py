from src.db import repository
from src.db.models import ActionType, ProposalStatus
from src.integrations.anthropic_client import MockAgentReasoningClient
from src.integrations.marketing_client import MarketingRegistry, MockMarketingClient
from src.workflows.pipeline import (
    DecisionResult,
    execute_autonomously,
    execute_stuck_awaiting_telegram_proposals,
    handle_telegram_decision,
    send_for_telegram_approval,
    submit_proposal,
)

from .conftest import all_approving_agents


def test_submit_proposal_cj_order_has_no_spending_cap_however_large_the_cost(conn, settings):
    # Owner's explicit instruction, 2026-10-14: "ليس هناك سقف الانفاق مادام
    # الزبون هو من يدفع" - a CJ_ORDER proposal is always backed by a
    # Shopify order already reported as paid, so there is no cost ceiling
    # any more, however large - a real regression test for that removal.
    agents = all_approving_agents()

    proposal = submit_proposal(
        conn,
        action_type=ActionType.CJ_ORDER.value,
        payload={"shopify_order_id": "1001"},
        justification="test",
        cost=1_000_000.0,
        risk="low",
        proposed_by="test",
        settings=settings,
        agents=agents,
    )

    assert proposal.status == ProposalStatus.CONSENSUS_REACHED.value
    # Owner's 2026-10-18 instruction: no agent vote gates this any more -
    # no votes are ever recorded for a proposal going through submit_proposal().
    assert repository.get_votes_for_round(conn, proposal.id, 1) == []


def test_submit_proposal_within_limits_goes_straight_to_consensus_reached_with_no_agent_vote(conn, settings):
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
    assert repository.get_votes_for_round(conn, proposal.id, 1) == []
    assert agents[0]._client.calls == []  # the agent was never called for this gate


def test_submit_proposal_with_zero_profit_cost_breakdown_is_auto_rejected(conn, settings):
    # Owner's explicit instruction, 2026-10-14: no fixed margin floor any
    # more - only a real, fee-inclusive profit of zero or less is rejected.
    agents = all_approving_agents()

    proposal = submit_proposal(
        conn,
        action_type=ActionType.PUBLISH_PRODUCT.value,
        payload={
            "title": "x",
            "cost_breakdown": {
                "sale_price": 100,
                "product_cost": 100,
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


def test_submit_proposal_with_a_thin_but_real_margin_reaches_consensus(conn, settings):
    # The exact case the owner said must now pass: only 5% margin, which the
    # old 25% MIN_MARGIN floor would have auto-rejected before any agent
    # ever saw it.
    agents = all_approving_agents()

    proposal = submit_proposal(
        conn,
        action_type=ActionType.PUBLISH_PRODUCT.value,
        payload={
            "title": "x",
            "cost_breakdown": {
                "sale_price": 100,
                "product_cost": 95,
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

    assert proposal.status == ProposalStatus.CONSENSUS_REACHED.value


def test_send_for_telegram_approval_requires_consensus_reached_first(conn, settings, telegram):
    agents = all_approving_agents()
    proposal = submit_proposal(
        conn,
        action_type=ActionType.PUBLISH_PRODUCT.value,
        payload={
            "title": "x",
            "cost_breakdown": {
                "sale_price": 100,
                "product_cost": 100,
                "shipping_cost": 0,
                "shopify_fee": 0,
                "payment_processing_fee": 0,
            },
        },
        justification="t",
        cost=0,
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


# --- Owner's 2026-10-14 full-autonomy instruction: no approval gate for any
# action_type, including the real sale - see pipeline.py's module docstring.


def test_execute_autonomously_requires_consensus_reached_first(conn, settings, telegram, executor):
    agents = all_approving_agents()
    proposal = submit_proposal(
        conn, action_type=ActionType.PUBLISH_PRODUCT.value,
        payload={
            "title": "x",
            "cost_breakdown": {
                "sale_price": 100, "product_cost": 100, "shipping_cost": 0,
                "shopify_fee": 0, "payment_processing_fee": 0,
            },
        },
        justification="t", cost=0, risk="low", proposed_by="test", settings=settings, agents=agents,
    )
    assert proposal.status == ProposalStatus.AUTO_REJECTED.value

    try:
        execute_autonomously(conn, proposal, executor, agents, telegram)
        assert False, "expected ValueError for a non-consensus-reached proposal"
    except ValueError:
        pass
    assert telegram.sent == []
    assert telegram.notifications == []


def test_execute_autonomously_executes_publish_product_with_no_telegram_message_at_all(
    conn, settings, telegram, executor, shopify
):
    agents = all_approving_agents()
    proposal = submit_proposal(
        conn, action_type=ActionType.PUBLISH_PRODUCT.value,
        payload={"title": "x", "description": "d", "price": 9.99},
        justification="t", cost=0, risk="low", proposed_by="test", settings=settings, agents=agents,
    )
    assert proposal.status == ProposalStatus.CONSENSUS_REACHED.value

    result = execute_autonomously(conn, proposal, executor, agents, telegram)

    assert result.proposal.status == ProposalStatus.EXECUTED.value
    # Not the real sale - no button request AND no plain notification either.
    assert telegram.sent == []
    assert telegram.notifications == []


def test_execute_autonomously_on_a_real_cj_order_sends_a_post_sale_notification(
    conn, settings, telegram, executor, cj
):
    # dry_run=False so the executor actually calls the (mock) supplier and
    # the result is a real, non-dry-run success - the one case that must
    # notify. Without this flip the notification branch is never reached at
    # all, which is exactly the regression this test guards against.
    settings.dry_run = False
    agents = all_approving_agents()
    proposal = submit_proposal(
        conn, action_type=ActionType.CJ_ORDER.value,
        payload={
            "shopify_order_id": "SHOP-9",
            "line_items": [{"cj_product_id": "CJ-1", "quantity": 1}],
            "shipping_address": {"country": "US"},
        },
        justification="t", cost=25.0, risk="low", proposed_by="test", settings=settings, agents=agents,
    )
    assert proposal.status == ProposalStatus.CONSENSUS_REACHED.value

    result = execute_autonomously(conn, proposal, executor, agents, telegram)

    assert result.proposal.status == ProposalStatus.EXECUTED.value
    assert cj.orders  # a real (mock) supplier order was actually created
    assert telegram.sent == []  # no approve/reject buttons
    assert len(telegram.notifications) == 1
    assert f"#{proposal.id}" in telegram.notifications[0]
    assert "SHOP-9" in telegram.notifications[0]
    assert "25.0" in telegram.notifications[0]


def test_execute_autonomously_does_not_notify_on_execution_failure(conn, settings, telegram, executor):
    settings.dry_run = False
    agents = all_approving_agents()
    # No cj_product_id in the line item -> executor._execute_real() raises,
    # caught by Executor.execute() as {"success": False, ...}.
    proposal = submit_proposal(
        conn, action_type=ActionType.CJ_ORDER.value,
        payload={"shopify_order_id": "SHOP-9", "line_items": [{"quantity": 1}], "shipping_address": {}},
        justification="t", cost=25.0, risk="low", proposed_by="test", settings=settings, agents=agents,
    )

    result = execute_autonomously(conn, proposal, executor, agents, telegram)

    assert result.proposal.status == ProposalStatus.EXECUTION_FAILED.value
    assert telegram.notifications == []


def test_execute_stuck_awaiting_telegram_proposals_executes_without_a_tap(
    conn, settings, telegram, executor
):
    # Owner's 2026-10-14 instruction landed with a real proposal already
    # sitting in Telegram with buttons, never tapped - under full autonomy
    # it must execute on its own rather than wait forever.
    agents = all_approving_agents()
    proposal = submit_proposal(
        conn, action_type=ActionType.PUBLISH_PRODUCT.value,
        payload={"title": "x", "description": "d", "price": 9.99},
        justification="t", cost=0, risk="low", proposed_by="test", settings=settings, agents=agents,
    )
    send_for_telegram_approval(conn, proposal, telegram)
    assert repository.get_proposal(conn, proposal.id).status == ProposalStatus.AWAITING_TELEGRAM.value

    executed_count = execute_stuck_awaiting_telegram_proposals(conn, executor, agents, telegram)

    assert executed_count == 1
    assert repository.get_proposal(conn, proposal.id).status == ProposalStatus.EXECUTED.value


def test_execute_stuck_awaiting_telegram_proposals_ignores_other_statuses(conn, settings, telegram, executor):
    agents = all_approving_agents()
    proposal = submit_proposal(
        conn, action_type=ActionType.PUBLISH_PRODUCT.value,
        payload={"title": "x", "description": "d", "price": 9.99},
        justification="t", cost=0, risk="low", proposed_by="test", settings=settings, agents=agents,
    )
    # Still at consensus_reached, never sent - must be untouched by the
    # awaiting_telegram-only catch-up.
    executed_count = execute_stuck_awaiting_telegram_proposals(conn, executor, agents, telegram)

    assert executed_count == 0
    assert repository.get_proposal(conn, proposal.id).status == ProposalStatus.CONSENSUS_REACHED.value


# --- Owner's 2026-10-18 instruction ("ابحث انت و قرر الافضل"): promote a
# real published product on every configured marketing platform.

def test_execute_autonomously_promotes_a_real_published_product_on_configured_platforms(
    conn, settings, telegram, executor, shopify
):
    settings.dry_run = False
    agents = all_approving_agents()
    marketing_platform = MockMarketingClient()
    marketing = MarketingRegistry({"telegram": marketing_platform})
    proposal = submit_proposal(
        conn, action_type=ActionType.PUBLISH_PRODUCT.value,
        payload={"title": "Slim Wallet", "description": "A slim wallet", "price": 19.99, "images": ["https://x/img.jpg"]},
        justification="t", cost=0, risk="low", proposed_by="test", settings=settings, agents=agents,
    )

    marketing_reasoning_client = MockAgentReasoningClient(["check out this slim wallet!"])

    result = execute_autonomously(conn, proposal, executor, agents, telegram, marketing, marketing_reasoning_client)

    assert result.proposal.status == ProposalStatus.EXECUTED.value
    assert len(marketing_platform.posts) == 1
    assert marketing_reasoning_client.calls  # the dedicated Gemini-role client generated the copy
    actions = [row[0] for row in conn.execute("SELECT action FROM audit_log").fetchall()]
    assert "product_promoted" in actions


def test_execute_autonomously_does_not_promote_in_dry_run(conn, settings, telegram, executor):
    assert settings.dry_run is True
    agents = all_approving_agents()
    marketing_platform = MockMarketingClient()
    marketing = MarketingRegistry({"telegram": marketing_platform})
    proposal = submit_proposal(
        conn, action_type=ActionType.PUBLISH_PRODUCT.value,
        payload={"title": "x", "description": "d", "price": 9.99, "images": []},
        justification="t", cost=0, risk="low", proposed_by="test", settings=settings, agents=agents,
    )

    execute_autonomously(conn, proposal, executor, agents, telegram, marketing)

    assert marketing_platform.posts == []


def test_execute_autonomously_does_not_promote_a_cj_order(conn, settings, telegram, executor, cj):
    settings.dry_run = False
    agents = all_approving_agents()
    marketing_platform = MockMarketingClient()
    marketing = MarketingRegistry({"telegram": marketing_platform})
    proposal = submit_proposal(
        conn, action_type=ActionType.CJ_ORDER.value,
        payload={
            "shopify_order_id": "SHOP-9",
            "line_items": [{"cj_product_id": "CJ-1", "quantity": 1}],
            "shipping_address": {"country": "US"},
        },
        justification="t", cost=25.0, risk="low", proposed_by="test", settings=settings, agents=agents,
    )

    execute_autonomously(conn, proposal, executor, agents, telegram, marketing)

    assert marketing_platform.posts == []


def test_execute_autonomously_with_no_marketing_registry_does_not_crash(conn, settings, telegram, executor):
    settings.dry_run = False
    agents = all_approving_agents()
    proposal = submit_proposal(
        conn, action_type=ActionType.PUBLISH_PRODUCT.value,
        payload={"title": "x", "description": "d", "price": 9.99},
        justification="t", cost=0, risk="low", proposed_by="test", settings=settings, agents=agents,
    )

    result = execute_autonomously(conn, proposal, executor, agents, telegram)  # marketing omitted entirely

    assert result.proposal.status == ProposalStatus.EXECUTED.value
