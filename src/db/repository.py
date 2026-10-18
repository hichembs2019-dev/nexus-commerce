"""All SQL lives here - every other module calls these functions instead of
writing its own queries, so the audit trail and schema stay in one place.
"""
from __future__ import annotations

import json
import sqlite3

from .models import AgentVote, Proposal


def create_proposal(
    conn: sqlite3.Connection,
    *,
    action_type: str,
    payload: dict,
    justification: str,
    cost: float,
    risk: str,
    proposed_by: str,
) -> Proposal:
    cur = conn.execute(
        """INSERT INTO proposals
           (action_type, payload_json, justification, cost, risk, status, round, proposed_by)
           VALUES (?, ?, ?, ?, ?, 'pending_review', 1, ?)""",
        (action_type, json.dumps(payload), justification, cost, risk, proposed_by),
    )
    conn.commit()
    return get_proposal(conn, cur.lastrowid)


def get_proposal(conn: sqlite3.Connection, proposal_id: int) -> Proposal:
    row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
    return _row_to_proposal(row)


def get_proposals_by_status(conn: sqlite3.Connection, status: str) -> list[Proposal]:
    rows = conn.execute("SELECT * FROM proposals WHERE status = ? ORDER BY id", (status,)).fetchall()
    return [_row_to_proposal(row) for row in rows]


def update_proposal_status(conn: sqlite3.Connection, proposal_id: int, status: str) -> None:
    conn.execute(
        "UPDATE proposals SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, proposal_id),
    )
    conn.commit()


def update_proposal_round(
    conn: sqlite3.Connection, proposal_id: int, round_number: int, payload: dict | None = None
) -> None:
    if payload is None:
        conn.execute(
            "UPDATE proposals SET round = ?, updated_at = datetime('now') WHERE id = ?",
            (round_number, proposal_id),
        )
    else:
        conn.execute(
            "UPDATE proposals SET round = ?, payload_json = ?, updated_at = datetime('now') WHERE id = ?",
            (round_number, json.dumps(payload), proposal_id),
        )
    conn.commit()


def record_vote(
    conn: sqlite3.Connection,
    *,
    proposal_id: int,
    round_number: int,
    agent_name: str,
    vote: str,
    reason: str,
    amended_payload: dict | None = None,
) -> AgentVote:
    cur = conn.execute(
        """INSERT INTO agent_votes
           (proposal_id, round, agent_name, vote, reason, amended_payload_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            proposal_id,
            round_number,
            agent_name,
            vote,
            reason,
            json.dumps(amended_payload) if amended_payload is not None else None,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM agent_votes WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_vote(row)


def get_votes_for_round(conn: sqlite3.Connection, proposal_id: int, round_number: int) -> list[AgentVote]:
    rows = conn.execute(
        "SELECT * FROM agent_votes WHERE proposal_id = ? AND round = ? ORDER BY id",
        (proposal_id, round_number),
    ).fetchall()
    return [_row_to_vote(r) for r in rows]


def record_telegram_send(conn: sqlite3.Connection, proposal_id: int, message_id: str | None) -> int:
    cur = conn.execute(
        "INSERT INTO telegram_approvals (proposal_id, message_id) VALUES (?, ?)",
        (proposal_id, message_id),
    )
    conn.commit()
    return cur.lastrowid


def get_latest_telegram_approval_id(conn: sqlite3.Connection, proposal_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM telegram_approvals WHERE proposal_id = ? ORDER BY id DESC LIMIT 1",
        (proposal_id,),
    ).fetchone()
    return row["id"] if row else None


def record_telegram_decision(conn: sqlite3.Connection, approval_id: int, decision: str) -> None:
    conn.execute(
        "UPDATE telegram_approvals SET decision = ?, decided_at = datetime('now') WHERE id = ?",
        (decision, approval_id),
    )
    conn.commit()


def create_order(
    conn: sqlite3.Connection,
    *,
    proposal_id: int,
    shopify_order_id: str,
    cost: float,
) -> int:
    cur = conn.execute(
        """INSERT INTO orders (proposal_id, shopify_order_id, status, cost)
           VALUES (?, ?, 'pending', ?)""",
        (proposal_id, shopify_order_id, cost),
    )
    conn.commit()
    return cur.lastrowid


def update_order_cj(conn: sqlite3.Connection, order_id: int, cj_order_id: str, status: str) -> None:
    conn.execute(
        "UPDATE orders SET cj_order_id = ?, status = ?, updated_at = datetime('now') WHERE id = ?",
        (cj_order_id, status, order_id),
    )
    conn.commit()


def update_order_tracking(conn: sqlite3.Connection, order_id: int, tracking_number: str) -> None:
    conn.execute(
        "UPDATE orders SET tracking_number = ?, updated_at = datetime('now') WHERE id = ?",
        (tracking_number, order_id),
    )
    conn.commit()


def order_exists_for_shopify_order(conn: sqlite3.Connection, shopify_order_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM orders WHERE shopify_order_id = ?", (shopify_order_id,)
    ).fetchone()
    return row is not None


def publish_product_proposal_exists(conn: sqlite3.Connection, cj_product_id: str) -> bool:
    """Found live 2026-10-18, before this was ever deployed: discover_new_products()
    has no dedup at all against a candidate already proposed/published -
    unlike every other workflow here (order_fulfillment's own
    order_exists_for_shopify_order() above, price_inventory_review and
    tracking_update's own "not re-proposed" checks). Run on a schedule
    (owner wants new-product-discovery wired into the real 10-minute
    GitHub Actions cron, not just a once-a-day call nobody triggers), the
    SAME profitable CJ search result would be found and PUBLISHED AGAIN as
    a brand new duplicate Shopify listing every single firing - the exact
    "found live, fixed before it broke something real" pattern this
    project's whole history follows, just caught before deployment instead
    of after. `consensus_reached`/`executed` only - a `auto_rejected` or
    `execution_failed` attempt is allowed to be retried (conditions, e.g. a
    margin that was briefly negative, can change).
    """
    row = conn.execute(
        """SELECT 1 FROM proposals
           WHERE action_type = 'publish_product'
             AND json_extract(payload_json, '$.cj_product_id') = ?
             AND status IN ('consensus_reached', 'executed')
           LIMIT 1""",
        (cj_product_id,),
    ).fetchone()
    return row is not None


def audit(conn: sqlite3.Connection, *, actor: str, action: str, details: dict) -> None:
    conn.execute(
        "INSERT INTO audit_log (actor, action, details_json) VALUES (?, ?, ?)",
        (actor, action, json.dumps(details)),
    )
    conn.commit()


def get_order_by_proposal_id(conn: sqlite3.Connection, proposal_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM orders WHERE proposal_id = ?", (proposal_id,)).fetchone()


def get_orders_with_cj_order(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Orders that have actually been placed with CJ (cj_order_id set) -
    candidates for the hourly tracking-update check.
    """
    return conn.execute(
        "SELECT * FROM orders WHERE cj_order_id IS NOT NULL"
    ).fetchall()




def _row_to_proposal(row: sqlite3.Row) -> Proposal:
    return Proposal(
        id=row["id"],
        action_type=row["action_type"],
        payload=json.loads(row["payload_json"]),
        justification=row["justification"],
        cost=row["cost"],
        risk=row["risk"],
        status=row["status"],
        round=row["round"],
        proposed_by=row["proposed_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_vote(row: sqlite3.Row) -> AgentVote:
    return AgentVote(
        id=row["id"],
        proposal_id=row["proposal_id"],
        round=row["round"],
        agent_name=row["agent_name"],
        vote=row["vote"],
        reason=row["reason"],
        amended_payload=json.loads(row["amended_payload_json"]) if row["amended_payload_json"] else None,
        created_at=row["created_at"],
    )
