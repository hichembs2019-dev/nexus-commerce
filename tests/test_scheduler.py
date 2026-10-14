from src.app import App
from src.db import repository
from src.db.models import ProposalStatus
from src.integrations.telegram_client import MockTelegramClient
from src.scheduler import resend_stuck_consensus_reached_proposals


def _make_app(conn) -> App:
    telegram = MockTelegramClient()
    return App(
        settings=None,
        conn=conn,
        shopify=None,
        cj=None,
        suppliers=None,
        telegram=telegram,
        web_search=None,
        agents=[],
        executor=None,
    )


def _consensus_reached_proposal(conn):
    proposal = repository.create_proposal(
        conn, action_type="publish_product", payload={"title": "x"}, justification="t", cost=0, risk="low", proposed_by="test"
    )
    repository.update_proposal_status(conn, proposal.id, ProposalStatus.CONSENSUS_REACHED.value)
    return repository.get_proposal(conn, proposal.id)


def test_a_proposal_stuck_at_consensus_reached_is_sent_to_telegram_on_the_sweep(conn):
    # Found live 2026-10-14: a real proposal the agents already agreed on
    # never reached the owner because the service was restarted before
    # run_daily()'s own send step (which only sees proposals it just
    # created) got to it - this is exactly that scenario, reproduced.
    proposal = _consensus_reached_proposal(conn)
    app = _make_app(conn)

    resent_count = resend_stuck_consensus_reached_proposals(app)

    assert resent_count == 1
    result = repository.get_proposal(conn, proposal.id)
    assert result.status == ProposalStatus.AWAITING_TELEGRAM.value
    assert len(app.telegram.sent) == 1


def test_a_proposal_not_at_consensus_reached_is_left_untouched(conn):
    proposal = repository.create_proposal(
        conn, action_type="publish_product", payload={"title": "x"}, justification="t", cost=0, risk="low", proposed_by="test"
    )  # default status is pending_review, not consensus_reached
    app = _make_app(conn)

    resent_count = resend_stuck_consensus_reached_proposals(app)

    assert resent_count == 0
    result = repository.get_proposal(conn, proposal.id)
    assert result.status == ProposalStatus.PENDING_REVIEW.value
    assert len(app.telegram.sent) == 0
