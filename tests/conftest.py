from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.agent import Agent, AGENT_NAMES
from src.config import Settings
from src.db.database import init_db
from src.integrations.anthropic_client import MockAgentReasoningClient
from src.integrations.cj_client import MockCJClient
from src.integrations.shopify_client import MockShopifyClient
from src.integrations.telegram_client import MockTelegramClient
from src.tools.web_search import MockWebSearchTool
from src.workflows.executor import Executor


@pytest.fixture()
def conn(tmp_path):
    database_path = tmp_path / "test.db"
    connection = init_db(database_path)
    yield connection
    connection.close()


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(
        database_path=str(tmp_path / "test.db"),
        max_order_cost=200.0,
        daily_spend_limit=500.0,
        min_margin=0.25,
        dry_run=True,
    )


def approving_reasoning_client() -> MockAgentReasoningClient:
    return MockAgentReasoningClient([json.dumps({"vote": "approve", "reason": "looks fine", "amended_payload": None})])


def rejecting_reasoning_client(reason: str = "too risky") -> MockAgentReasoningClient:
    return MockAgentReasoningClient([json.dumps({"vote": "reject", "reason": reason, "amended_payload": None})])


def amending_reasoning_client(amended_payload: dict, reason: str = "let's tweak this") -> MockAgentReasoningClient:
    return MockAgentReasoningClient(
        [json.dumps({"vote": "amend", "reason": reason, "amended_payload": amended_payload})]
    )


def build_agents(reasoning_clients: list) -> list[Agent]:
    assert len(reasoning_clients) == 5
    return [Agent(name, client) for name, client in zip(AGENT_NAMES, reasoning_clients)]


def all_approving_agents() -> list[Agent]:
    return build_agents([approving_reasoning_client() for _ in range(5)])


@pytest.fixture()
def shopify():
    return MockShopifyClient()


@pytest.fixture()
def cj():
    return MockCJClient()


@pytest.fixture()
def telegram():
    return MockTelegramClient()


@pytest.fixture()
def web_search():
    return MockWebSearchTool()


@pytest.fixture()
def executor(shopify, cj, settings):
    return Executor(shopify, cj, settings)
