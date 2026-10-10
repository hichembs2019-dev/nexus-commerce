import json

from src.agents.agent import Agent
from src.agents.post_execution_review import review_execution
from src.db import repository
from src.db.models import ActionType, ProposalStatus
from src.integrations.anthropic_client import MockAgentReasoningClient

AGENT_NAMES = ("A1", "A2", "A3", "A4", "A5")


def _agents(replies: list[str]) -> list[Agent]:
    assert len(replies) == 5
    return [Agent(name, MockAgentReasoningClient([reply])) for name, reply in zip(AGENT_NAMES, replies)]


def _approve():
    return json.dumps({"vote": "approve", "reason": "looks correct", "amended_payload": None})


def _amend(payload, reason="needs a fix"):
    return json.dumps({"vote": "amend", "reason": reason, "amended_payload": payload})


def test_unanimous_approval_of_the_result_opens_no_correction(conn):
    executed = repository.create_proposal(
        conn, action_type=ActionType.CJ_ORDER.value, payload={}, justification="t", cost=10, risk="low", proposed_by="test"
    )
    agents = _agents([_approve()] * 5)

    correction = review_execution(conn, agents, executed, {"success": True, "detail": "ok"})

    assert correction is None


def test_an_agent_finding_an_error_with_a_concrete_fix_opens_a_correction_proposal(conn):
    executed = repository.create_proposal(
        conn, action_type=ActionType.CJ_ORDER.value, payload={"quantity": 1}, justification="t", cost=10, risk="low", proposed_by="test"
    )
    fix = {"quantity": 1, "shipping_address": {"country": "US"}}
    agents = _agents([_approve(), _approve(), _approve(), _approve(), _amend(fix, "missing shipping address")])

    correction = review_execution(conn, agents, executed, {"success": False, "detail": "missing shipping address"})

    assert correction is not None
    assert correction.action_type == ActionType.CORRECTION.value
    assert correction.payload == fix
    assert correction.status == ProposalStatus.PENDING_REVIEW.value  # awaits a real consensus run, not auto-approved


def test_an_error_found_with_no_concrete_fix_logs_but_opens_no_correction(conn):
    from src.agents.agent import AgentDecision

    class _RejectingAgent(Agent):
        def review(self, proposal, prior_round_votes):
            return AgentDecision(vote="reject", reason="something is wrong, not sure what to do")

    executed = repository.create_proposal(
        conn, action_type=ActionType.CJ_ORDER.value, payload={}, justification="t", cost=10, risk="low", proposed_by="test"
    )
    agents = [_RejectingAgent(name, MockAgentReasoningClient([])) for name in AGENT_NAMES]

    correction = review_execution(conn, agents, executed, {"success": False, "detail": "unknown error"})

    assert correction is None
