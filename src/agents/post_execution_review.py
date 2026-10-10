"""Spec step 6: "بعد التنفيذ: الخمسة يراجعون النتيجة. إن وُجد خطأ، يُفتح
مقترح تصحيح بنفس البروتوكول." (after execution, the five review the
result; if an error is found, a correction proposal is opened using the
same protocol.)

This is a single review round, not a 3-round negotiation - its job is
detection ("did this go wrong"), not deciding what to do about it. If any
agent amends with a correction payload, that becomes a new, separate
proposal row (action_type CORRECTION) left at pending_review for the caller
to run through the real `run_consensus` (the full protocol the spec calls
for) - this function does not approve anything on its own.
"""
from __future__ import annotations

import sqlite3

from ..db import repository
from ..db.models import ActionType, Proposal, ProposalStatus
from .agent import Agent


def review_execution(
    conn: sqlite3.Connection, agents: list[Agent], executed_proposal: Proposal, execution_result: dict
) -> Proposal | None:
    review_payload = {
        "original_proposal_id": executed_proposal.id,
        "original_action_type": executed_proposal.action_type,
        "original_payload": executed_proposal.payload,
        "execution_result": execution_result,
    }
    review_row = repository.create_proposal(
        conn,
        action_type=ActionType.EXECUTION_REVIEW.value,
        payload=review_payload,
        justification=f"post-execution review of proposal #{executed_proposal.id}",
        cost=0,
        risk="",
        proposed_by="system:post_execution_review",
    )

    decisions = []
    for agent in agents:
        decision = _review_with_fallback(agent, review_row)
        repository.record_vote(
            conn,
            proposal_id=review_row.id,
            round_number=1,
            agent_name=agent.name,
            vote=decision.vote,
            reason=decision.reason,
            amended_payload=decision.amended_payload,
        )
        decisions.append(decision)

    found_error = any(d.vote != "approve" for d in decisions)
    repository.update_proposal_status(
        conn, review_row.id, ProposalStatus.EXECUTED.value if not found_error else ProposalStatus.FAILED_CONSENSUS.value
    )

    if not found_error:
        return None

    correction_payload = next(
        (d.amended_payload for d in decisions if d.vote == "amend" and d.amended_payload), None
    )
    if correction_payload is None:
        # Agents flagged a problem but none proposed a concrete fix - there
        # is nothing actionable to turn into a correction proposal. Logged,
        # not silently dropped.
        repository.audit(
            conn,
            actor="post_execution_review",
            action="error_found_no_correction_proposed",
            details={"original_proposal_id": executed_proposal.id, "review_id": review_row.id},
        )
        return None

    correction = repository.create_proposal(
        conn,
        action_type=ActionType.CORRECTION.value,
        payload=correction_payload,
        justification=f"correction for proposal #{executed_proposal.id} (execution review #{review_row.id})",
        cost=executed_proposal.cost,
        risk=executed_proposal.risk,
        proposed_by="system:post_execution_review",
    )
    repository.audit(
        conn,
        actor="post_execution_review",
        action="correction_proposed",
        details={"original_proposal_id": executed_proposal.id, "correction_proposal_id": correction.id},
    )
    return correction


def _review_with_fallback(agent: Agent, review_row: Proposal):
    from .agent import AgentDecision

    try:
        return agent.review(review_row, [])
    except Exception as exc:  # noqa: BLE001 - same reasoning as consensus.py
        return AgentDecision(vote="reject", reason=f"agent call failed: {exc}")
