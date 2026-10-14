"""Ties spec steps 1-6 together end to end:
submit_proposal (auto-limits -> consensus) -> execute_autonomously (execute ->
post-execution review).

Owner's explicit instruction, 2026-10-14 ("الاستقلالية التامة و العامة...
لا اقدر ان ابقى خلفهم على الموافقة او لا" - full, general autonomy, I cannot
stay behind them approving or not): there is no Telegram approve/reject gate
for ANY action_type any more, including CJ_ORDER (the real sale) - a
CONSENSUS_REACHED proposal executes immediately (see execute_autonomously()
and scheduler.py). Telegram is used only to notify the owner AFTER a real
CJ_ORDER has actually executed ("انا ارى الارباح و بس" - I just see the
results), since that is the one message the owner asked to still receive.

send_for_telegram_approval/handle_telegram_decision are kept only so any
proposal already sent to Telegram with real Approve/Reject buttons *before*
this change (sitting in a real chat, AWAITING_TELEGRAM in the database)
still works if the owner taps one - nothing new is ever routed through that
path again. execute_stuck_awaiting_telegram_proposals() closes the gap for
ones nobody ever taps.

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
from ..tools.limits import LimitCheckResult, check_margin
from ..tools.profit_calculator import CostBreakdown
from .executor import Executor


def _check_limits(action_type: str, payload: dict) -> LimitCheckResult:
    # Owner's explicit instruction, 2026-10-14: no spending cap on CJ_ORDER
    # ("ليس هناك سقف الانفاق مادام الزبون هو من يدفع" - no spending cap since
    # it's the customer who pays). This is actually safe to remove, not just
    # permitted: order_fulfillment.py only ever creates a CJ_ORDER proposal
    # for a Shopify order whose financial_status Shopify itself already
    # reports as "paid" (check_payment_confirmed, enforced there before this
    # function is ever reached) - the money being spent here is always
    # revenue already received, never a speculative purchase.
    if action_type == ActionType.CJ_ORDER.value:
        return LimitCheckResult(allowed=True)

    if "cost_breakdown" in payload:
        breakdown = CostBreakdown(**payload["cost_breakdown"])
        return check_margin(breakdown)

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

    limit_result = _check_limits(action_type, payload)
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
    """Not called by anything new any more (see module docstring) - kept so
    any already-AWAITING_TELEGRAM proposal from before the full-autonomy
    change, and its test coverage, still works.
    """
    if proposal.status != ProposalStatus.CONSENSUS_REACHED.value:
        raise ValueError(
            f"proposal {proposal.id} has status={proposal.status!r}, not consensus_reached - "
            "only a proposal the 5 agents actually agreed on may be sent to Telegram"
        )

    message_id = telegram_client.send_approval_request(proposal.id, _format_summary(proposal))
    repository.record_telegram_send(conn, proposal.id, message_id)
    repository.update_proposal_status(conn, proposal.id, ProposalStatus.AWAITING_TELEGRAM.value)
    return repository.get_proposal(conn, proposal.id)


def _format_sale_notification(proposal: Proposal, result: dict) -> str:
    """The owner's own words for what this message is for: "انا ارى الارباح
    و بس" (I just see the results) - only the real, already-known numbers:
    what the customer actually paid (proposal.cost, the Shopify order total)
    and the supplier order CJ actually created. No profit figure is invented
    here - per-sale product cost is not tracked anywhere in this database yet
    (see docs/UNVERIFIED.md), so a "profit" line would be a guess, which the
    owner has repeatedly and explicitly forbidden.
    """
    return (
        f"✅ تم تنفيذ عملية بيع حقيقية بشكل تلقائي بالكامل\n"
        f"مقترح #{proposal.id} | طلب Shopify: {proposal.payload.get('shopify_order_id')}\n"
        f"قيمة البيع (ما دفعه الزبون): {proposal.cost}\n"
        f"{result.get('detail', '')}"
    )


def _execute_and_finalize(
    conn: sqlite3.Connection,
    proposal: Proposal,
    executor: Executor,
    agents: list[Agent],
    telegram_client,
) -> DecisionResult:
    """Shared by every real execution path (autonomous, catch-up, and the
    legacy Telegram-approve path) so EXECUTED/EXECUTION_FAILED, the audit
    entry, order-linking, the post-sale notification and the post-execution
    review are done identically regardless of how execution was reached.
    """
    result = executor.execute(proposal)
    final_status = ProposalStatus.EXECUTED if result["success"] else ProposalStatus.EXECUTION_FAILED
    repository.update_proposal_status(conn, proposal.id, final_status.value)
    repository.audit(
        conn,
        actor="executor",
        action=final_status.value,
        details={"proposal_id": proposal.id, "result": result, "autonomous": True},
    )
    _link_order_result(conn, proposal, result)

    if proposal.action_type == ActionType.CJ_ORDER.value and result.get("success") and not result.get("dry_run"):
        telegram_client.send_notification(_format_sale_notification(proposal, result))

    executed_proposal = repository.get_proposal(conn, proposal.id)
    correction = review_execution(conn, agents, executed_proposal, result)
    return DecisionResult(proposal=executed_proposal, correction_proposal=correction)


def execute_autonomously(
    conn: sqlite3.Connection,
    proposal: Proposal,
    executor: Executor,
    agents: list[Agent],
    telegram_client,
) -> DecisionResult:
    """The only path a brand-new CONSENSUS_REACHED proposal goes through now
    (see scheduler.py) - no Telegram approve/reject step for any
    action_type, per the owner's explicit full-autonomy instruction.
    """
    if proposal.status != ProposalStatus.CONSENSUS_REACHED.value:
        raise ValueError(
            f"proposal {proposal.id} has status={proposal.status!r}, not consensus_reached - "
            "only a proposal the agents actually agreed on may be executed autonomously"
        )
    repository.audit(
        conn, actor="autopilot", action="autonomous_execution_started", details={"proposal_id": proposal.id}
    )
    return _execute_and_finalize(conn, proposal, executor, agents, telegram_client)


def execute_stuck_awaiting_telegram_proposals(
    conn: sqlite3.Connection, executor: Executor, agents: list[Agent], telegram_client
) -> int:
    """One-time catch-up for any proposal sent to Telegram with real
    Approve/Reject buttons before the full-autonomy change, that the owner
    never got to tap - under the new policy nothing is meant to wait on a
    human tap at all, so these execute now instead of sitting forever. Call
    once at startup, same spirit as resend_stuck_consensus_reached_proposals
    (now execute_stuck_consensus_reached_proposals) in scheduler.py.
    """
    stuck = repository.get_proposals_by_status(conn, ProposalStatus.AWAITING_TELEGRAM.value)
    for proposal in stuck:
        repository.audit(
            conn,
            actor="autopilot",
            action="awaiting_telegram_auto_executed",
            details={"proposal_id": proposal.id, "reason": "full-autonomy policy change, 2026-10-14"},
        )
        _execute_and_finalize(conn, proposal, executor, agents, telegram_client)
    return len(stuck)


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
