"""Executor.execute()'s real (non-DRY_RUN) CJ_ORDER path has no other
coverage - test_e2e_dry_run.py only ever runs with DRY_RUN=true, which
short-circuits before _execute_real() is ever reached. Found live
2026-10-14: that path read payload["product_id"]/payload["quantity"]
directly, but order_fulfillment.py's real payload only ever carries
"line_items" - this would have raised a real KeyError on the very first
real paid order.
"""
from __future__ import annotations

from src.config import Settings
from src.db import repository
from src.db.models import ActionType
from src.integrations.cj_client import MockCJClient
from src.integrations.shopify_client import MockShopifyClient
from src.integrations.supplier_client import SupplierRegistry
from src.workflows.executor import Executor


def _settings(**overrides) -> Settings:
    base = dict(dry_run=False)
    base.update(overrides)
    return Settings(**base)


def _cj_order_proposal(conn, payload: dict):
    proposal = repository.create_proposal(
        conn, action_type=ActionType.CJ_ORDER.value, payload=payload, justification="t", cost=10, risk="low", proposed_by="test"
    )
    return proposal


def test_a_single_line_item_order_is_placed_with_its_cj_product_id(conn):
    cj = MockCJClient()
    executor = Executor(MockShopifyClient(), SupplierRegistry({"cj": cj}), _settings())
    proposal = _cj_order_proposal(
        conn,
        {
            "shopify_order_id": "SHOP-1",
            "line_items": [{"cj_product_id": "CJ-1", "quantity": 2}],
            "shipping_address": {"country_code": "US"},
        },
    )

    result = executor.execute(proposal)

    assert result["success"] is True
    assert len(cj.orders) == 1
    order = next(iter(cj.orders.values()))
    assert order["product_id"] == "CJ-1"
    assert order["quantity"] == 2


def test_the_real_shopify_order_id_is_threaded_through_as_the_cj_order_number(conn):
    # Closes docs/UNVERIFIED.md's other flagged gap: orderNumber used to be
    # a locally-generated uuid4 with no real meaning.
    cj = MockCJClient()
    executor = Executor(MockShopifyClient(), SupplierRegistry({"cj": cj}), _settings())
    proposal = _cj_order_proposal(
        conn,
        {
            "shopify_order_id": "SHOP-REAL-42",
            "line_items": [{"cj_product_id": "CJ-1", "quantity": 1}],
            "shipping_address": {"country_code": "US"},
        },
    )

    executor.execute(proposal)

    order = next(iter(cj.orders.values()))
    assert order["shipping_address"]["order_number"] == "SHOP-REAL-42"


def test_an_order_with_more_than_one_line_item_fails_clearly_not_partially(conn):
    # Real scope gap (CJClient.create_order() takes one product/quantity
    # pair): must surface clearly, never silently fulfil only the first
    # item while charging the customer for all of them.
    cj = MockCJClient()
    executor = Executor(MockShopifyClient(), SupplierRegistry({"cj": cj}), _settings())
    proposal = _cj_order_proposal(
        conn,
        {
            "shopify_order_id": "SHOP-2",
            "line_items": [
                {"cj_product_id": "CJ-1", "quantity": 1},
                {"cj_product_id": "CJ-2", "quantity": 1},
            ],
            "shipping_address": {"country_code": "US"},
        },
    )

    result = executor.execute(proposal)

    assert result["success"] is False
    assert "line item" in result["detail"]
    assert cj.orders == {}  # never partially fulfilled


def test_a_line_item_with_no_cj_product_id_fails_clearly(conn):
    # A real line item whose product was never published with the
    # cj_product_id metafield (or isn't a product at all) - must not guess
    # which supplier product to order.
    cj = MockCJClient()
    executor = Executor(MockShopifyClient(), SupplierRegistry({"cj": cj}), _settings())
    proposal = _cj_order_proposal(
        conn,
        {
            "shopify_order_id": "SHOP-3",
            "line_items": [{"cj_product_id": "", "quantity": 1}],
            "shipping_address": {"country_code": "US"},
        },
    )

    result = executor.execute(proposal)

    assert result["success"] is False
    assert "cj_product_id" in result["detail"]
    assert cj.orders == {}
