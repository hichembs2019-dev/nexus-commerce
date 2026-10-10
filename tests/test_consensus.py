import json

from src.agents.agent import Agent
from src.agents.consensus import MAX_ROUNDS, run_consensus
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


# --- spec-required case: consensus (all 5 approve) ---

def test_unanimous_approval_in_round_1_reaches_consensus(conn):
    proposal = _make_proposal(conn)
    agents = _agents([[_approve()] for _ in range(5)])

    result = run_consensus(conn, proposal, agents)

    assert result.status == ProposalStatus.CONSENSUS_REACHED.value
    assert result.round == 1
    votes = repository.get_votes_for_round(conn, proposal.id, 1)
    assert len(votes) == 5
    assert all(v.vote == "approve" for v in votes)


# --- spec-required case: rejection ---

def test_a_single_reject_prevents_consensus_in_that_round(conn):
    proposal = _make_proposal(conn)
    # 4 approve round 1, 1 rejects round 1; all approve round 2.
    agents = _agents(
        [
            [_approve(), _approve()],
            [_approve(), _approve()],
            [_approve(), _approve()],
            [_approve(), _approve()],
            [_reject("too expensive"), _approve()],
        ]
    )

    result = run_consensus(conn, proposal, agents)

    assert result.status == ProposalStatus.CONSENSUS_REACHED.value
    assert result.round == 2
    round1_votes = repository.get_votes_for_round(conn, proposal.id, 1)
    assert any(v.vote == "reject" and v.reason == "too expensive" for v in round1_votes)


def test_rejection_that_never_resolves_fails_after_max_rounds(conn):
    proposal = _make_proposal(conn)
    # A5 rejects every single round, no one ever amends.
    agents = _agents(
        [
            [_approve()] * MAX_ROUNDS,
            [_approve()] * MAX_ROUNDS,
            [_approve()] * MAX_ROUNDS,
            [_approve()] * MAX_ROUNDS,
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
    agents = _agents(
        [
            [_approve(), _approve()],
            [_approve(), _approve()],
            [_approve(), _approve()],
            [_approve(), _approve()],
            [_amend(amended, "need more stock"), _approve()],
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
    agents = _agents(
        [
            [_approve(), _approve()],
            [_amend(a2_amendment), _approve()],
            [_approve(), _approve()],
            [_amend(a4_amendment), _approve()],
            [_approve(), _approve()],
        ]
    )

    result = run_consensus(conn, proposal, agents)

    # Documented design choice in consensus.py: first amendment in agent
    # order (A1..A5) wins - here that's A2's, not A4's.
    assert result.payload == a2_amendment


# --- spec-required case: failure after 3 rounds (no consensus reached at all) ---

def test_never_reaching_consensus_after_3_rounds_is_marked_failed_and_cancelled(conn):
    proposal = _make_proposal(conn)
    # Every round: 4 approve, 1 keeps amending to a new value - literal
    # unanimous approval of one exact version never happens.
    agents = _agents(
        [
            [_approve()] * MAX_ROUNDS,
            [_approve()] * MAX_ROUNDS,
            [_approve()] * MAX_ROUNDS,
            [_approve()] * MAX_ROUNDS,
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
    # A5's round-1 reply is garbage; everyone (including A5) approves in
    # every later round, scripted explicitly so this test's outcome depends
    # only on round 1's parse failure, not on later rounds running out of
    # scripted replies.
    agents = _agents(
        [
            [_approve()] * MAX_ROUNDS,
            [_approve()] * MAX_ROUNDS,
            [_approve()] * MAX_ROUNDS,
            [_approve()] * MAX_ROUNDS,
            ["this is not json at all", _approve(), _approve()],
        ]
    )

    result = run_consensus(conn, proposal, agents)

    round1_votes = repository.get_votes_for_round(conn, proposal.id, 1)
    a5_round1_vote = next(v for v in round1_votes if v.agent_name == "A5")
    assert a5_round1_vote.vote == "reject"
    # Having been treated as a reject (not a silent approve), round 1 does
    # NOT reach consensus - it only reaches it in round 2, once A5's real
    # (parseable) reply is an actual approve.
    assert result.status == ProposalStatus.CONSENSUS_REACHED.value
    assert result.round == 2
