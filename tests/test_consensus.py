import json

from src.agents.agent import Agent
from src.agents.consensus import MAX_ROUNDS, MIN_APPROVALS, run_consensus
from src.db import repository
from src.db.models import ProposalStatus
from src.integrations.anthropic_client import MockAgentReasoningClient

AGENT_NAMES = ("A1", "A2", "A3", "A4", "A5")


def _agents(replies_per_agent: list[list[str]]) -> list[Agent]:
    assert len(replies_per_agent) == 5
    return [Agent(name, MockAgentReasoningClient(replies)) for name, replies in zip(AGENT_NAMES, replies_per_agent)]


def _approve(reason="fine"):
    return json.dumps({"vote": "approve", "reason": reason, "amended_payload": None})


def _reject(reason="no"):
    return json.dumps({"vote": "reject", "reason": reason, "amended_payload": None})


def _amend(payload, reason="tweak it"):
    return json.dumps({"vote": "amend", "reason": reason, "amended_payload": payload})


def _make_proposal(conn):
    return repository.create_proposal(
        conn,
        action_type="cj_order",
        payload={"quantity": 1},
        justification="test",
        cost=10.0,
        risk="low",
        proposed_by="test",
    )


# --- owner's explicit instruction (2026-10-14): MIN_APPROVALS = 2, not 5/5 ---
# Real reason, see src/agents/consensus.py's module doc: strict 5/5 reached
# consensus 0 times out of 20 real candidates over ~4.5 hours of real
# operation under the free Gemini tier's real failure rate.

def test_unanimous_approval_in_round_1_reaches_consensus(conn):
    proposal = _make_proposal(conn)
    agents = _agents([[_approve()] for _ in range(5)])

    result = run_consensus(conn, proposal, agents)

    assert result.status == ProposalStatus.CONSENSUS_REACHED.value
    assert result.round == 1
    votes = repository.get_votes_for_round(conn, proposal.id, 1)
    assert len(votes) == 5
    assert all(v.vote == "approve" for v in votes)


def test_exactly_min_approvals_reaches_consensus_even_with_a_majority_rejecting(conn):
    # The owner's own explicit threshold: 2 of 5, not a majority of 3.
    assert MIN_APPROVALS == 2
    proposal = _make_proposal(conn)
    agents = _agents(
        [
            [_approve()],
            [_approve()],
            [_reject("too expensive")],
            [_reject("too expensive")],
            [_reject("too expensive")],
        ]
    )

    result = run_consensus(conn, proposal, agents)

    assert result.status == ProposalStatus.CONSENSUS_REACHED.value
    assert result.round == 1


def test_fewer_than_min_approvals_does_not_reach_consensus_in_that_round(conn):
    proposal = _make_proposal(conn)
    # Only 1 approval in round 1 (below MIN_APPROVALS=2); 2 approvals in
    # round 2 clears it.
    agents = _agents(
        [
            [_approve(), _approve()],
            [_reject("no"), _approve()],
            [_reject("no"), _reject("no")],
            [_reject("no"), _reject("no")],
            [_reject("no"), _reject("no")],
        ]
    )

    result = run_consensus(conn, proposal, agents)

    assert result.status == ProposalStatus.CONSENSUS_REACHED.value
    assert result.round == 2
    round1_votes = repository.get_votes_for_round(conn, proposal.id, 1)
    assert sum(1 for v in round1_votes if v.vote == "approve") == 1  # below MIN_APPROVALS


def test_rejection_that_never_resolves_fails_after_max_rounds(conn):
    proposal = _make_proposal(conn)
    # Only 1 approval every round (below MIN_APPROVALS=2) - never clears it.
    agents = _agents(
        [
            [_approve()] * MAX_ROUNDS,
            [_reject("never")] * MAX_ROUNDS,
            [_reject("never")] * MAX_ROUNDS,
            [_reject("never")] * MAX_ROUNDS,
            [_reject("never")] * MAX_ROUNDS,
        ]
    )

    result = run_consensus(conn, proposal, agents)

    assert result.status == ProposalStatus.FAILED_CONSENSUS.value
    assert result.round == MAX_ROUNDS


# --- spec-required case: amendment ---

def test_an_amendment_becomes_the_candidate_payload_for_the_next_round(conn):
    proposal = _make_proposal(conn)
    amended = {"quantity": 2}
    # Round 1: only 1 approval (below MIN_APPROVALS) so the amendment is
    # actually picked up for round 2, where it clears the threshold.
    agents = _agents(
        [
            [_approve(), _approve()],
            [_reject("no"), _approve()],
            [_reject("no"), _reject("no")],
            [_reject("no"), _reject("no")],
            [_amend(amended, "need more stock"), _reject("no")],
        ]
    )

    result = run_consensus(conn, proposal, agents)

    assert result.status == ProposalStatus.CONSENSUS_REACHED.value
    assert result.round == 2
    assert result.payload == amended


def test_two_different_amendments_in_one_round_the_first_agent_order_wins(conn):
    proposal = _make_proposal(conn)
    a2_amendment = {"quantity": 2}
    a4_amendment = {"quantity": 4}
    # Round 1: 0 approvals (below MIN_APPROVALS), two different amendments -
    # the first in agent order (A2) is picked as round 2's candidate.
    agents = _agents(
        [
            [_reject("no"), _approve()],
            [_amend(a2_amendment), _approve()],
            [_reject("no"), _reject("no")],
            [_amend(a4_amendment), _reject("no")],
            [_reject("no"), _approve()],
        ]
    )

    result = run_consensus(conn, proposal, agents)

    # Documented design choice in consensus.py: first amendment in agent
    # order (A1..A5) wins - here that's A2's, not A4's.
    assert result.payload == a2_amendment
    assert result.status == ProposalStatus.CONSENSUS_REACHED.value


def test_never_reaching_consensus_after_3_rounds_is_marked_failed_and_cancelled(conn):
    proposal = _make_proposal(conn)
    # Every round: at most 1 approval (below MIN_APPROVALS=2) - the
    # threshold is never cleared across all 3 rounds.
    agents = _agents(
        [
            [_approve()] * MAX_ROUNDS,
            [_reject("no")] * MAX_ROUNDS,
            [_reject("no")] * MAX_ROUNDS,
            [_reject("no")] * MAX_ROUNDS,
            [_amend({"quantity": 2}), _amend({"quantity": 3}), _amend({"quantity": 4})],
        ]
    )

    result = run_consensus(conn, proposal, agents)

    assert result.status == ProposalStatus.FAILED_CONSENSUS.value
    assert result.round == MAX_ROUNDS
    # All 3 rounds got persisted - nothing silently skipped.
    for round_number in range(1, MAX_ROUNDS + 1):
        assert len(repository.get_votes_for_round(conn, proposal.id, round_number)) == 5


def test_an_unparseable_agent_reply_is_treated_as_a_reject_not_a_crash_or_silent_approve(conn):
    proposal = _make_proposal(conn)
    # Round 1: 1 real approval + A5's garbage reply. If the garbage reply
    # were silently treated as an approve, round 1 would wrongly reach
    # MIN_APPROVALS=2 right here. Treated correctly as a reject, it stays
    # at 1 approval and consensus is only reached in round 2, once A5's
    # real (parseable) reply is an actual approve.
    agents = _agents(
        [
            [_approve()] * MAX_ROUNDS,
            [_reject("no"), _approve()],
            [_reject("no"), _reject("no")],
            [_reject("no"), _reject("no")],
            ["this is not json at all", _approve(), _approve()],
        ]
    )

    result = run_consensus(conn, proposal, agents)

    round1_votes = repository.get_votes_for_round(conn, proposal.id, 1)
    a5_round1_vote = next(v for v in round1_votes if v.agent_name == "A5")
    assert a5_round1_vote.vote == "reject"
    assert result.status == ProposalStatus.CONSENSUS_REACHED.value
    assert result.round == 2
