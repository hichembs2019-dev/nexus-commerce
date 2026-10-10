"""One Agent class, instantiated 5 times as A1..A5 - identical system
prompt, identical reasoning client type, identical permissions (none of them
can themselves call Shopify/CJ/Telegram; see consensus.py and the
executor, which are the only things that ever do). Nothing distinguishes one
agent from another except the name used in the audit trail.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..db.models import AgentVote, Proposal
from ..integrations.anthropic_client import AgentReasoningClient
from .prompts import AGENT_SYSTEM_PROMPT, build_review_prompt

AGENT_NAMES = ("A1", "A2", "A3", "A4", "A5")


@dataclass
class AgentDecision:
    vote: str  # "approve" | "reject" | "amend"
    reason: str
    amended_payload: dict | None = None


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def parse_agent_decision(raw_text: str) -> AgentDecision:
    """Agents are instructed to reply with JSON only, but models sometimes
    wrap it in prose or code fences anyway - this pulls out the first
    {...} block rather than requiring an exact match. Raises ValueError on
    anything that still doesn't parse into the expected shape; the caller
    (consensus.py) decides how to treat that (see its own doc comment: a
    failure to parse is treated as a reject, never as a silent approve).
    """
    match = _JSON_BLOCK.search(raw_text)
    if not match:
        raise ValueError(f"no JSON object found in agent reply: {raw_text!r}")

    data = json.loads(match.group(0))

    vote = data.get("vote")
    if vote not in ("approve", "reject", "amend"):
        raise ValueError(f"agent reply has an invalid 'vote': {vote!r}")

    reason = data.get("reason", "")
    amended_payload = data.get("amended_payload")

    if vote == "amend" and not isinstance(amended_payload, dict):
        raise ValueError("agent voted 'amend' but gave no amended_payload object")

    return AgentDecision(vote=vote, reason=reason, amended_payload=amended_payload)


def _summarize_proposal(proposal: Proposal) -> str:
    return json.dumps(
        {
            "action_type": proposal.action_type,
            "payload": proposal.payload,
            "justification": proposal.justification,
            "cost": proposal.cost,
            "risk": proposal.risk,
        },
        ensure_ascii=False,
        indent=2,
    )


def _summarize_prior_votes(votes: list[AgentVote]) -> str | None:
    if not votes:
        return None
    lines = []
    for v in votes:
        line = f"- {v.agent_name}: {v.vote} - {v.reason}"
        if v.amended_payload is not None:
            line += f" (amended_payload: {json.dumps(v.amended_payload, ensure_ascii=False)})"
        lines.append(line)
    return "\n".join(lines)


class Agent:
    def __init__(self, name: str, reasoning_client: AgentReasoningClient):
        self.name = name
        self._client = reasoning_client

    def review(self, proposal: Proposal, prior_round_votes: list[AgentVote]) -> AgentDecision:
        user_prompt = build_review_prompt(
            _summarize_proposal(proposal), _summarize_prior_votes(prior_round_votes)
        )
        raw = self._client.complete(AGENT_SYSTEM_PROMPT, user_prompt)
        return parse_agent_decision(raw)


def build_five_agents(reasoning_clients: list[AgentReasoningClient]) -> list[Agent]:
    if len(reasoning_clients) != 5:
        raise ValueError("exactly 5 reasoning clients are required, one per agent (spec: A1..A5)")
    return [Agent(name, client) for name, client in zip(AGENT_NAMES, reasoning_clients)]
