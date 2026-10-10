from src.db import repository
from src.db.models import ProposalStatus
from src.integrations.cj_client import CJProduct, TrackingInfo
from src.integrations.shopify_client import ShopifyOrder, ShopifyProduct
from src.workflows.new_product_discovery import discover_new_products
from src.workflows.order_fulfillment import check_new_paid_orders
from src.workflows.price_inventory_review import review_prices_and_inventory
from src.workflows.tracking_update import update_tracking_numbers

from .conftest import all_approving_agents


# ---- order_fulfillment ----------------------------------------------------

def test_a_paid_order_is_proposed_and_recorded_so_it_is_never_proposed_twice(conn, settings, shopify):
    shopify.orders.append(
        ShopifyOrder(order_id="SHOP-1", financial_status="paid", total_price=40.0, line_items=[{"sku": "x"}])
    )
    agents = all_approving_agents()

    proposals = check_new_paid_orders(conn, shopify, settings, agents)

    assert len(proposals) == 1
    assert proposals[0].status == ProposalStatus.CONSENSUS_REACHED.value
    assert repository.order_exists_for_shopify_order(conn, "SHOP-1")

    # a second hourly pass must not re-propose the same order
    again = check_new_paid_orders(conn, shopify, settings, agents)
    assert again == []


def test_an_unpaid_order_is_skipped_not_proposed(conn, settings, shopify):
    shopify.orders.append(ShopifyOrder(order_id="SHOP-2", financial_status="pending", total_price=40.0))

    proposals = check_new_paid_orders(conn, shopify, settings, agents=all_approving_agents())

    assert proposals == []
    assert not repository.order_exists_for_shopify_order(conn, "SHOP-2")


# ---- tracking_update --------------------------------------------------------

def _seed_order(conn, shopify_order_id: str, cost: float = 10.0) -> int:
    dummy_proposal = repository.create_proposal(
        conn, action_type="cj_order", payload={}, justification="t", cost=cost, risk="low", proposed_by="test"
    )
    return repository.create_order(conn, proposal_id=dummy_proposal.id, shopify_order_id=shopify_order_id, cost=cost)


def test_a_new_tracking_number_from_cj_is_proposed(conn, settings, cj):
    order_id = _seed_order(conn, "SHOP-1")
    repository.update_order_cj(conn, order_id, "mock-cj-order-1", status="ordered")
    cj.orders["mock-cj-order-1"] = {"product_id": "p1", "quantity": 1, "shipping_address": {}}
    cj.set_tracking("mock-cj-order-1", TrackingInfo(status="shipped", tracking_number="TRACK1", carrier="DHL"))

    proposals = update_tracking_numbers(conn, cj, settings, agents=all_approving_agents())

    assert len(proposals) == 1
    assert proposals[0].payload == {"order_id": "SHOP-1", "tracking_number": "TRACK1", "carrier": "DHL"}
    assert proposals[0].status == ProposalStatus.CONSENSUS_REACHED.value


def test_no_tracking_number_yet_is_skipped(conn, settings, cj):
    order_id = _seed_order(conn, "SHOP-1")
    repository.update_order_cj(conn, order_id, "mock-cj-order-1", status="ordered")
    cj.set_tracking("mock-cj-order-1", TrackingInfo(status="processing", tracking_number=""))

    proposals = update_tracking_numbers(conn, cj, settings, agents=all_approving_agents())

    assert proposals == []


def test_an_unchanged_tracking_number_is_not_re_proposed(conn, settings, cj):
    order_id = _seed_order(conn, "SHOP-1")
    repository.update_order_cj(conn, order_id, "mock-cj-order-1", status="ordered")
    repository.update_order_tracking(conn, order_id, "TRACK1")
    cj.set_tracking("mock-cj-order-1", TrackingInfo(status="shipped", tracking_number="TRACK1", carrier="DHL"))

    proposals = update_tracking_numbers(conn, cj, settings, agents=all_approving_agents())

    assert proposals == []


# ---- price_inventory_review -------------------------------------------------

def test_a_meaningful_supplier_price_change_is_proposed_at_the_configured_min_margin(conn, settings, shopify, cj):
    shopify.products.append(
        ShopifyProduct(product_id="P1", title="Widget", price=20.0, inventory=5, cj_product_id="CJ-1")
    )
    cj.catalog.append(CJProduct(product_id="CJ-1", title="Widget", price=12.0))  # far from the listed 20.0

    proposals = review_prices_and_inventory(conn, shopify, cj, settings, agents=all_approving_agents())

    assert len(proposals) == 1
    assert proposals[0].payload["product_id"] == "P1"
    assert proposals[0].payload["new_price"] == 16.0  # 12 / (1 - min_margin 0.25)


def test_a_product_with_no_cj_link_is_skipped(conn, settings, shopify, cj):
    shopify.products.append(ShopifyProduct(product_id="P1", title="Widget", price=20.0, inventory=5, cj_product_id=""))

    proposals = review_prices_and_inventory(conn, shopify, cj, settings, agents=all_approving_agents())

    assert proposals == []


def test_a_price_change_under_the_threshold_is_not_proposed(conn, settings, shopify, cj):
    shopify.products.append(
        ShopifyProduct(product_id="P1", title="Widget", price=20.0, inventory=5, cj_product_id="CJ-1")
    )
    cj.catalog.append(CJProduct(product_id="CJ-1", title="Widget", price=19.2))  # <5% away from the listed 20.0

    proposals = review_prices_and_inventory(conn, shopify, cj, settings, agents=all_approving_agents())

    assert proposals == []


# ---- new_product_discovery --------------------------------------------------

def test_a_product_clearing_min_margin_is_proposed_for_publishing(conn, settings, cj, web_search):
    cj.catalog.append(CJProduct(product_id="CJ-1", title="Phone Case", price=5.0))

    proposals = discover_new_products(
        conn, cj, web_search, settings, agents=all_approving_agents(), search_queries=["phone"]
    )

    assert len(proposals) == 1
    assert proposals[0].payload["cj_product_id"] == "CJ-1"
    assert proposals[0].payload["price"] == 10.0  # 2x markup
    assert proposals[0].status == ProposalStatus.CONSENSUS_REACHED.value


def test_a_product_with_zero_price_is_skipped(conn, settings, cj, web_search):
    cj.catalog.append(CJProduct(product_id="CJ-1", title="Phone Case", price=0.0))

    proposals = discover_new_products(
        conn, cj, web_search, settings, agents=all_approving_agents(), search_queries=["phone"]
    )

    assert proposals == []
