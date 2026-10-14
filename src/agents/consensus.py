"""Spec's consensus protocol, steps 1-4 (step 5, Telegram, and step 6,
post-execution review, live in telegram_gate.py and executor.py). This
module owns exactly: running up to 3 rounds, recording every vote, deciding
whether enough approval was reached, and what happens to the payload when it
wasn't.

Owner's own explicit, direct instruction (2026-10-14), after a real,
measured result: under the live operating conditions of this session (free
Gemini tier, 1-minute discovery cadence), strict 5/5 literal unanimity
reached consensus **zero times out of 20 real candidates** over ~4.5 hours
of real operation - not because any candidate was bad, but because getting
5 consecutive successful, agreeing real API calls (up to 3 rounds) is
statistically very hard at that failure rate. The owner was shown this
real count before deciding. MIN_APPROVALS below is that explicit choice -
"صيغها اثنان على خمسة 2/5" - not a guess or a default this project picked
on its own.

Documented design decisions this spec left open (see README.md and
docs/ for mutation-testing on each):

1. **Multiple different amendments in the same round**: the spec does not
   say how to reconcile e.g. A2 and A4 proposing two different amended
   payloads in the same round. This picks the FIRST amendment in agent
   order (A1 before A5) as the next round's candidate - simple, deterministic,
   and visible in the audit trail (every agent's own amendment is still
   recorded in agent_votes regardless of which one "won").
2. **An agent reply that fails to parse as the required JSON** (a model
   hiccup, not a real vote) is treated as an automatic "reject" with the
   parse error as the reason - never as a silent approve, which would be
   the one failure mode that could accidentally let something through
   unreviewed.
3. **A round where every agent rejects and none amend**: the payload is
   unchanged going into the next round (there is nothing to change it to),
   but agents now see that round's rejection reasons - they may change
   their mind, or may not; after round 3 either way, FAILED_CONSENSUS.
"""
from __future__ import annotations

import sqlite3
from dataclasses import replace

from ..db import repository
from ..db.models import Proposal, ProposalStatus
from .agent import Agent, parse_agent_decision

MAX_ROUNDS = 3
MIN_APPROVALS = 2  # out of 5 - owner's explicit instruction, see module doc


def run_consensus(conn: sqlite3.Connection, proposal: Proposal, agents: list[Agent]) -> Proposal:
    current_payload = proposal.payload

    for round_number in range(1, MAX_ROUNDS + 1):
        prior_votes = (
            repository.get_votes_for_round(conn, proposal.id, round_number - 1)
            if round_number > 1
            else []
        )
        round_proposal = replace(proposal, payload=current_payload, round=round_number)

        decisions = []
        for agent in agents:
            decision = _review_with_fallback(agent, round_proposal, prior_votes)
            repository.record_vote(
                conn,
                proposal_id=proposal.id,
                round_number=round_number,
                agent_name=agent.name,
                vote=decision.vote,
                reason=decision.reason,
                amended_payload=decision.amended_payload,
            )
            decisions.append(decision)

        repository.update_proposal_round(conn, proposal.id, round_number, current_payload)

        approve_count = sum(1 for d in decisions if d.vote == "approve")
        if approve_count >= MIN_APPROVALS:
            repository.update_proposal_status(conn, proposal.id, ProposalStatus.CONSENSUS_REACHED.value)
            repository.audit(
                conn,
                actor="consensus_engine",
                action="consensus_reached",
                details={
                    "proposal_id": proposal.id,
                    "round": round_number,
                    "approve_count": approve_count,
                    "total_agents": len(agents),
                },
            )
            return repository.get_proposal(conn, proposal.id)

        amendments = [d.amended_payload for d in decisions if d.vote == "amend" and d.amended_payload]
        if amendments:
            current_payload = amendments[0]  # see module doc point 1

    repository.update_proposal_status(conn, proposal.id, ProposalStatus.FAILED_CONSENSUS.value)
    repository.audit(
        conn,
        actor="consensus_engine",
        action="failed_consensus",
        details={"proposal_id": proposal.id, "rounds": MAX_ROUNDS},
    )
    return repository.get_proposal(conn, proposal.id)


def _review_with_fallback(agent: Agent, proposal: Proposal, prior_votes):
    """Any failure - a reply that doesn't parse as the required JSON, or a
    real API error from a live Anthropic call - degrades to an automatic
    reject (see module doc point 2), never a crash of the whole consensus
    run and never a silent approve.
    """
    try:
        return agent.review(proposal, prior_votes)
    except Exception as exc:  # noqa: BLE001 - intentionally broad, see above
        from .agent import AgentDecision

        return AgentDecision(vote="reject", reason=f"agent call failed: {exc}")
