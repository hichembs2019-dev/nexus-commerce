"""Plain dataclasses for what the database rows mean - kept separate from
database.py's schema so callers never format SQL by hand outside
repository.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ProposalStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    CONSENSUS_REACHED = "consensus_reached"
    FAILED_CONSENSUS = "failed_consensus"
    AUTO_REJECTED = "auto_rejected"
    AWAITING_TELEGRAM = "awaiting_telegram"
    TELEGRAM_APPROVED = "telegram_approved"
    TELEGRAM_REJECTED = "telegram_rejected"
    EXECUTED = "executed"
    EXECUTION_FAILED = "execution_failed"


class Vote(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    AMEND = "amend"


class ActionType(str, Enum):
    CJ_ORDER = "cj_order"
    PUBLISH_PRODUCT = "publish_product"
    UPDATE_PRICE = "update_price"
    UPDATE_TRACKING = "update_tracking"
    CORRECTION = "correction"
    EXECUTION_REVIEW = "execution_review"


@dataclass
class Proposal:
    id: int | None
    action_type: str
    payload: dict
    justification: str
    cost: float
    risk: str
    status: str
    round: int
    proposed_by: str
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class AgentVote:
    id: int | None
    proposal_id: int
    round: int
    agent_name: str
    vote: str
    reason: str
    amended_payload: dict | None = None
    created_at: str | None = None
