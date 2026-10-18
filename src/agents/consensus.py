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
real count before deciding. 2/5 was that explicit first choice -
"صيغها اثنان على خمسة 2/5".

That number dropped to 2/2 when the agent count itself dropped to 2
(2026-10-14), and even at 2/2 the real database (`nexus_commerce.db`,
checked live 2026-10-18) still showed 34 of 38 real publish_product
proposals FAILED_CONSENSUS and exactly zero real orders ever placed - the
same free-tier reasoning failure rate this module's history already
describes, just at smaller numbers. Owner's next explicit instruction
(2026-10-18): "اترك وكيل واحد يعمل ... الاذكى ... و يريد ان يشتغل" (leave
one agent working, the smartest one, that wants to work) - one real,
reliable agent (Claude, see src/app.py's reasoning-provider order) whose
own single "approve" is the whole decision. MIN_APPROVALS below is that
explicit choice now: 1 out of 1, not a guess.

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
MIN_APPROVALS = 1  # out of 1 agent now - owner's explicit instruction, see module doc


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

        amendments = [
            _unwrap_if_envelope_shaped(conn, proposal.id, round_number, d.amended_payload)
            for d in decisions
            if d.vote == "amend" and d.amended_payload
        ]
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


_ENVELOPE_KEYS = {"action_type", "justification", "cost", "risk"}


def _unwrap_if_envelope_shaped(conn: sqlite3.Connection, proposal_id: int, round_number: int, amended_payload: dict) -> dict:
    """An agent's amended_payload must be the flat product/order fields
    only - never the proposal's own envelope (action_type/payload/
    justification/cost/risk) that _summarize_proposal() shows the agent for
    context. Found live 2026-10-14: a real agent (A2, proposal #24, round 1)
    wrapped its amendment in exactly that envelope shape; the next round's
    peer review then saw an already-wrapped payload with nothing flat to
    anchor on, and both agents repeated the same mistake; round 3 approved
    it literally, and it was sent all the way to a real Shopify publish
    attempt, which failed with a real `execution error: 'title'` (a
    KeyError - the code looks for payload["title"], which only existed one
    level deeper, under payload["payload"]["title"]).

    If the amendment carries a nested "payload" dict alongside envelope
    keys, that inner dict is the real, intended amendment - unwrap it
    rather than silently propagate the wrapped shape into a 3rd round and
    then into execution. This is logged (never silent), since repairing
    malformed agent output is itself a signal the prompt needs attention.
    """
    if isinstance(amended_payload.get("payload"), dict) and _ENVELOPE_KEYS & amended_payload.keys():
        repository.audit(
            conn,
            actor="consensus_engine",
            action="amendment_envelope_unwrapped",
            details={"proposal_id": proposal_id, "round": round_number},
        )
        return amended_payload["payload"]
    return amended_payload


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
