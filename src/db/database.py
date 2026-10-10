"""SQLite schema and connection helper. Plain sqlite3 (stdlib) - this
project has no need for an ORM, and a hand-written schema is easier to audit
line by line than a migrations framework, which matters more than usual here
given spec SS6's "سجل تدقيق كامل لكل فعل" (a complete audit trail of every
action).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    justification TEXT NOT NULL,
    cost REAL NOT NULL DEFAULT 0,
    risk TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending_review',
    round INTEGER NOT NULL DEFAULT 1,
    proposed_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER NOT NULL REFERENCES proposals(id),
    round INTEGER NOT NULL,
    agent_name TEXT NOT NULL,
    vote TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    amended_payload_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS telegram_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER NOT NULL REFERENCES proposals(id),
    message_id TEXT,
    sent_at TEXT NOT NULL DEFAULT (datetime('now')),
    decision TEXT,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER REFERENCES proposals(id),
    shopify_order_id TEXT NOT NULL,
    cj_order_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    cost REAL NOT NULL DEFAULT 0,
    tracking_number TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_votes_proposal ON agent_votes(proposal_id, round);
CREATE INDEX IF NOT EXISTS idx_orders_proposal ON orders(proposal_id);
"""


def connect(database_path: str | Path) -> sqlite3.Connection:
    """One connection per caller - sqlite3 connections are not safe to share
    across threads, and APScheduler jobs each get their own.
    """
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(database_path: str | Path) -> sqlite3.Connection:
    conn = connect(database_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
