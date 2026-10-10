import pytest

from src.integrations.cj_client import CJProduct, MockCJClient, TrackingInfo


def test_search_products_matches_case_insensitively_by_substring():
    client = MockCJClient()
    client.catalog = [CJProduct(product_id="1", title="Phone Case", price=5.0), CJProduct(product_id="2", title="Pet Leash", price=7.0)]

    results = client.search_products("phone")

    assert [p.product_id for p in results] == ["1"]


def test_create_order_then_track_shipment_round_trips():
    client = MockCJClient()

    order_id = client.create_order(product_id="1", quantity=2, shipping_address={"country": "US"})
    tracking = client.track_shipment(order_id)

    assert tracking.status == "processing"
    assert order_id in client.orders
    assert client.orders[order_id]["quantity"] == 2


def test_set_tracking_helper_updates_what_track_shipment_returns():
    client = MockCJClient()
    order_id = client.create_order(product_id="1", quantity=1, shipping_address={})

    client.set_tracking(order_id, TrackingInfo(status="shipped", tracking_number="TRACK1", carrier="DHL"))

    assert client.track_shipment(order_id).tracking_number == "TRACK1"


def test_track_shipment_for_unknown_order_raises():
    client = MockCJClient()
    with pytest.raises(KeyError):
        client.track_shipment("does-not-exist")


def test_get_product_returns_catalog_entry_or_raises():
    client = MockCJClient()
    client.catalog = [CJProduct(product_id="1", title="Phone Case", price=5.0)]

    assert client.get_product("1").title == "Phone Case"
    with pytest.raises(KeyError):
        client.get_product("missing")
