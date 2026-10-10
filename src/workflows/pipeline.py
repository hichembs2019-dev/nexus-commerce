"""Ties spec steps 1-6 together end to end:
submit_proposal (auto-limits -> consensus) -> send_for_telegram_approval ->
handle_telegram_decision (execute -> post-execution review).

Kept as orchestration only - the actual rules live in tools/limits.py,
agents/consensus.py, workflows/executor.py, and
agents/post_execution_review.py; this module just calls them in order and
persists the result at each step.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..agents.agent import Agent
from ..agents.consensus import run_consensus
from ..agents.post_execution_review import review_execution
from ..config import Settings
from ..db import repository
from ..db.models import ActionType, Proposal, ProposalStatus
from ..tools.limits import LimitCheckResult, check_margin, check_order_limits
from ..tools.profit_calculator import CostBreakdown
from .executor import Executor


def _check_limits(action_type: str, payload: dict, cost: float, conn: sqlite3.Connection, settings: Settings) -> LimitCheckResult:
    if action_type == ActionType.CJ_ORDER.value:
        already_spent = repository.today_executed_spend(conn)
        return check_order_limits(cost, already_spent, settings)

    if "cost_breakdown" in payload:
        breakdown = CostBreakdown(**payload["cost_breakdown"])
        return check_margin(breakdown, settings)

    return LimitCheckResult(allowed=True)


def submit_proposal(
    conn: sqlite3.Connection,
    *,
    action_type: str,
    payload: dict,
    justification: str,
    cost: float,
    risk: str,
    proposed_by: str,
    settings: Settings,
    agents: list[Agent],
) -> Proposal:
    proposal = repository.create_proposal(
        conn,
        action_type=action_type,
        payload=payload,
        justification=justification,
        cost=cost,
        risk=risk,
        proposed_by=proposed_by,
    )

    limit_result = _check_limits(action_type, payload, cost, conn, settings)
    if not limit_result.allowed:
        repository.update_proposal_status(conn, proposal.id, ProposalStatus.AUTO_REJECTED.value)
        repository.audit(
            conn,
            actor="limits",
            action="auto_rejected",
            details={"proposal_id": proposal.id, "reason": limit_result.reason},
        )
        return repository.get_proposal(conn, proposal.id)

    return run_consensus(conn, proposal, agents)


def _format_summary(proposal: Proposal) -> str:
    return (
        f"مقترح #{proposal.id}: {proposal.action_type}\n"
        f"التكلفة: {proposal.cost}\n"
        f"المبرر: {proposal.justification}\n"
        f"المعطيات: {proposal.payload}"
    )


def send_for_telegram_approval(conn: sqlite3.Connection, proposal: Proposal, telegram_client) -> Proposal:
    if proposal.status != ProposalStatus.CONSENSUS_REACHED.value:
        raise ValueError(
            f"proposal {proposal.id} has status={proposal.status!r}, not consensus_reached - "
            "only a proposal the 5 agents actually agreed on may be sent to Telegram"
        )

    message_id = telegram_client.send_approval_request(proposal.id, _format_summary(proposal))
    repository.record_telegram_send(conn, proposal.id, message_id)
    repository.update_proposal_status(conn, proposal.id, ProposalStatus.AWAITING_TELEGRAM.value)
    return repository.get_proposal(conn, proposal.id)


def _link_order_result(conn: sqlite3.Connection, proposal: Proposal, result: dict) -> None:
    """A successfully executed CJ_ORDER proposal's cj_order_id needs to land
    on the `orders` row order_fulfillment.py already created when it was
    proposed - otherwise tracking_update.py would never find it. A DRY_RUN
    result has no real cj_order_id (nothing was actually ordered), so this
    only runs for a real, successful CJ_ORDER execution.
    """
    if not result.get("success") or result.get("dry_run"):
        return

    if proposal.action_type == ActionType.CJ_ORDER.value and "cj_order_id" in result:
        order_row = repository.get_order_by_proposal_id(conn, proposal.id)
        if order_row is not None:
            repository.update_order_cj(conn, order_row["id"], result["cj_order_id"], status="ordered")

    elif proposal.action_type == ActionType.UPDATE_TRACKING.value:
        shopify_order_id = proposal.payload.get("shopify_order_id") or proposal.payload.get("order_id")
        order_row = conn.execute(
            "SELECT id FROM orders WHERE shopify_order_id = ?", (shopify_order_id,)
        ).fetchone()
        if order_row is not None:
            repository.update_order_tracking(conn, order_row["id"], proposal.payload["tracking_number"])


@dataclass
class DecisionResult:
    proposal: Proposal
    correction_proposal: Proposal | None


def handle_telegram_decision(
    conn: sqlite3.Connection,
    proposal_id: int,
    decision: str,
    executor: Executor,
    agents: list[Agent],
) -> DecisionResult:
    if decision not in ("approve", "reject"):
        raise ValueError(f"invalid decision: {decision!r}")

    proposal = repository.get_proposal(conn, proposal_id)
    if proposal.status != ProposalStatus.AWAITING_TELEGRAM.value:
        raise ValueError(
            f"proposal {proposal_id} has status={proposal.status!r}, not awaiting_telegram - "
            "cannot record a Telegram decision for it"
        )

    approval_id = repository.get_latest_telegram_approval_id(conn, proposal_id)
    repository.record_telegram_decision(conn, approval_id, decision)

    if decision == "reject":
        repository.update_proposal_status(conn, proposal_id, ProposalStatus.TELEGRAM_REJECTED.value)
        repository.audit(conn, actor="owner", action="telegram_rejected", details={"proposal_id": proposal_id})
        return DecisionResult(proposal=repository.get_proposal(conn, proposal_id), correction_proposal=None)

    repository.update_proposal_status(conn, proposal_id, ProposalStatus.TELEGRAM_APPROVED.value)
    repository.audit(conn, actor="owner", action="telegram_approved", details={"proposal_id": proposal_id})

    result = executor.execute(proposal)
    final_status = ProposalStatus.EXECUTED if result["success"] else ProposalStatus.EXECUTION_FAILED
    repository.update_proposal_status(conn, proposal_id, final_status.value)
    repository.audit(
        conn,
        actor="executor",
        action=final_status.value,
        details={"proposal_id": proposal_id, "result": result},
    )
    _link_order_result(conn, proposal, result)

    executed_proposal = repository.get_proposal(conn, proposal_id)
    correction = review_execution(conn, agents, executed_proposal, result)
    return DecisionResult(proposal=executed_proposal, correction_proposal=correction)
