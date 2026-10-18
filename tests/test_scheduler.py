from src.app import App
from src.db import repository
from src.db.models import ProposalStatus
from src.integrations.anthropic_client import MockAgentReasoningClient
from src.integrations.marketing_client import MarketingRegistry
from src.integrations.telegram_client import MockTelegramClient
from src.scheduler import execute_stuck_consensus_reached_proposals

from .conftest import all_approving_agents


def _make_app(conn, settings, executor) -> App:
    telegram = MockTelegramClient()
    return App(
        settings=settings,
        conn=conn,
        shopify=None,
        cj=None,
        suppliers=None,
        telegram=telegram,
        web_search=None,
        marketing=MarketingRegistry({}),
        agents=all_approving_agents(),
        executor=executor,
        marketing_reasoning_client=MockAgentReasoningClient(),
    )


def _consensus_reached_proposal(conn, action_type="publish_product", payload=None, cost=0):
    proposal = repository.create_proposal(
        conn, action_type=action_type, payload=payload or {"title": "x"}, justification="t", cost=cost,
        risk="low", proposed_by="test",
    )
    repository.update_proposal_status(conn, proposal.id, ProposalStatus.CONSENSUS_REACHED.value)
    return repository.get_proposal(conn, proposal.id)


def test_a_proposal_stuck_at_consensus_reached_executes_autonomously_on_the_sweep(conn, settings, executor):
    # Found live 2026-10-14: a real proposal the agents already agreed on
    # never got acted on because the service was restarted before
    # run_daily()'s own step (which only sees proposals it just created) got
    # to it - this is exactly that scenario, reproduced. Owner's 2026-10-14
    # full-autonomy instruction means the sweep now executes it directly
    # instead of sending it to Telegram for approval.
    proposal = _consensus_reached_proposal(conn)
    app = _make_app(conn, settings, executor)

    executed_count = execute_stuck_consensus_reached_proposals(app)

    assert executed_count == 1
    result = repository.get_proposal(conn, proposal.id)
    assert result.status == ProposalStatus.EXECUTED.value
    # publish_product is not the real sale - no Telegram message at all.
    assert app.telegram.sent == []
    assert app.telegram.notifications == []


def test_the_sweep_respects_a_limit_and_leaves_the_rest_stuck_for_the_next_run(conn, settings, executor):
    # Found live 2026-10-18 (GitHub Actions runs 39158203166, 39159056431):
    # an unbounded sweep here was killed by the job's own wall-clock
    # timeout before finishing, and leaves the rest stuck for the next
    # run - which then tries to clear a bigger backlog, unbounded again.
    # A limit must execute exactly that many and leave the remainder
    # genuinely untouched (still consensus_reached), not merely claim to.
    proposals = [_consensus_reached_proposal(conn) for _ in range(3)]
    app = _make_app(conn, settings, executor)

    executed_count = execute_stuck_consensus_reached_proposals(app, limit=2)

    assert executed_count == 2
    statuses = [repository.get_proposal(conn, p.id).status for p in proposals]
    assert statuses.count(ProposalStatus.EXECUTED.value) == 2
    assert statuses.count(ProposalStatus.CONSENSUS_REACHED.value) == 1


def test_a_proposal_not_at_consensus_reached_is_left_untouched(conn, settings, executor):
    proposal = repository.create_proposal(
        conn, action_type="publish_product", payload={"title": "x"}, justification="t", cost=0, risk="low", proposed_by="test"
    )  # default status is pending_review, not consensus_reached
    app = _make_app(conn, settings, executor)

    executed_count = execute_stuck_consensus_reached_proposals(app)

    assert executed_count == 0
    result = repository.get_proposal(conn, proposal.id)
    assert result.status == ProposalStatus.PENDING_REVIEW.value
    assert app.telegram.sent == []
    assert app.telegram.notifications == []


def test_a_consensus_reached_cj_order_executing_in_dry_run_sends_no_notification(conn, settings, executor):
    # DRY_RUN (the test settings fixture's default) means nothing was really
    # ordered - a notification claiming a real sale happened would be false.
    assert settings.dry_run is True
    proposal = _consensus_reached_proposal(
        conn,
        action_type="cj_order",
        payload={"shopify_order_id": "1001", "line_items": [{"cj_product_id": "p1", "quantity": 1}], "shipping_address": {}},
        cost=10,
    )
    app = _make_app(conn, settings, executor)

    execute_stuck_consensus_reached_proposals(app)

    result = repository.get_proposal(conn, proposal.id)
    assert result.status == ProposalStatus.EXECUTED.value
    assert app.telegram.notifications == []
