"""Unit tests for the verified parts of RealShopifyClient: create_product()
(productCreate + productVariantsBulkCreate) and get_recent_orders() (the
orders connection + displayFinancialStatus). Verified 2026-10-11 - see
docs/SOURCES.md. shopify.GraphQL().execute() is faked here since it needs a
real Shopify session; everything above that call is real project code.
"""
from __future__ import annotations

import json

import pytest

from src.integrations.shopify_client import RealShopifyClient


class _FakeGraphQL:
    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def execute(self, *, query: str, variables: dict):
        self.calls.append((query, variables))
        return json.dumps(self._responses.pop(0))


def _client(responses: list[dict]) -> tuple[RealShopifyClient, _FakeGraphQL]:
    client = RealShopifyClient("test-shop.myshopify.com", "fake-client-id", "fake-client-secret", "2024-07")
    client._access_token = "faketoken"  # skip the real auth exchange - covered separately below
    fake = _FakeGraphQL(responses)
    client._shopify.GraphQL = lambda: fake
    return client, fake


class _FakeAuthResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_get_access_token_posts_client_credentials_and_returns_the_access_token(monkeypatch):
    client = RealShopifyClient("test-shop.myshopify.com", "fake-client-id", "fake-client-secret", "2024-07")

    calls = []

    def fake_post(url, *, headers, data, timeout):
        calls.append((url, headers, data))
        return _FakeAuthResponse({"access_token": "real-shopify-token", "scope": "read_products", "expires_in": 86399})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    token = client._get_access_token()

    assert token == "real-shopify-token"
    assert len(calls) == 1
    url, headers, data = calls[0]
    assert url == "https://test-shop.myshopify.com/admin/oauth/access_token"
    assert headers == {"Content-Type": "application/x-www-form-urlencoded"}
    assert data == {
        "grant_type": "client_credentials",
        "client_id": "fake-client-id",
        "client_secret": "fake-client-secret",
    }


def test_get_access_token_is_cached_and_not_refetched(monkeypatch):
    client = RealShopifyClient("test-shop.myshopify.com", "fake-client-id", "fake-client-secret", "2024-07")

    call_count = 0

    def fake_post(url, *, headers, data, timeout):
        nonlocal call_count
        call_count += 1
        return _FakeAuthResponse({"access_token": "tok"})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    client._get_access_token()
    client._get_access_token()

    assert call_count == 1


def test_get_access_token_raises_clearly_on_authentication_failure(monkeypatch):
    client = RealShopifyClient("test-shop.myshopify.com", "bad-id", "bad-secret", "2024-07")

    def fake_post(url, *, headers, data, timeout):
        return _FakeAuthResponse({"errors": "invalid_client"})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(RuntimeError, match="Shopify authentication failed"):
        client._get_access_token()


def test_create_product_calls_productCreate_then_productVariantsBulkCreate_and_returns_the_product_id():
    client, fake = _client(
        [
            {"data": {"productCreate": {"product": {"id": "gid://shopify/Product/1"}, "userErrors": []}}},
            {"data": {"productVariantsBulkCreate": {"productVariants": [{"id": "gid://shopify/ProductVariant/1"}], "userErrors": []}}},
        ]
    )

    product_id = client.create_product(
        title="Widget", description="d", price=19.99, images=["https://example.com/a.jpg"]
    )

    assert product_id == "gid://shopify/Product/1"
    assert len(fake.calls) == 2
    first_query, first_vars = fake.calls[0]
    assert "productCreate" in first_query
    assert first_vars["title"] == "Widget"
    assert first_vars["media"] == [{"originalSource": "https://example.com/a.jpg", "mediaContentType": "IMAGE", "alt": "Widget"}]

    second_query, second_vars = fake.calls[1]
    assert "productVariantsBulkCreate" in second_query
    assert second_vars["productId"] == "gid://shopify/Product/1"
    # Money is a bare decimal-string scalar, not a {amount, currencyCode}
    # object - found live on 2026-10-13 ("invalid money" from Shopify).
    assert second_vars["variants"] == [{"price": "19.99"}]
    assert second_vars["strategy"] == "REMOVE_STANDALONE_VARIANT"


def test_create_product_sends_no_metafields_when_no_cj_product_id_given():
    client, fake = _client(
        [
            {"data": {"productCreate": {"product": {"id": "gid://shopify/Product/1"}, "userErrors": []}}},
            {"data": {"productVariantsBulkCreate": {"productVariants": [{"id": "gid://shopify/ProductVariant/1"}], "userErrors": []}}},
        ]
    )

    client.create_product(title="Widget", description="d", price=19.99, images=[])

    _, first_vars = fake.calls[0]
    assert first_vars["metafields"] == []


def test_create_product_stores_cj_product_id_as_a_metafield():
    client, fake = _client(
        [
            {"data": {"productCreate": {"product": {"id": "gid://shopify/Product/1"}, "userErrors": []}}},
            {"data": {"productVariantsBulkCreate": {"productVariants": [{"id": "gid://shopify/ProductVariant/1"}], "userErrors": []}}},
        ]
    )

    client.create_product(
        title="Widget", description="d", price=19.99, images=[], cj_product_id="CJ-123"
    )

    _, first_vars = fake.calls[0]
    assert first_vars["metafields"] == [
        {"namespace": "nexus_commerce", "key": "cj_product_id", "type": "single_line_text_field", "value": "CJ-123"}
    ]


def test_get_products_maps_the_real_response_shape_including_the_cj_product_id_metafield():
    client, fake = _client(
        [
            {
                "data": {
                    "products": {
                        "edges": [
                            {
                                "node": {
                                    "id": "gid://shopify/Product/1",
                                    "title": "Widget",
                                    "totalInventory": 42,
                                    "priceRangeV2": {"minVariantPrice": {"amount": "19.99"}},
                                    "metafield": {"value": "CJ-123"},
                                }
                            }
                        ]
                    }
                }
            }
        ]
    )

    products = client.get_products()

    assert len(products) == 1
    product = products[0]
    assert product.product_id == "gid://shopify/Product/1"
    assert product.title == "Widget"
    assert product.price == 19.99
    assert product.inventory == 42
    assert product.cj_product_id == "CJ-123"


def test_get_products_defaults_cj_product_id_to_empty_string_when_metafield_is_null():
    client, fake = _client(
        [
            {
                "data": {
                    "products": {
                        "edges": [
                            {
                                "node": {
                                    "id": "gid://shopify/Product/2",
                                    "title": "No CJ link",
                                    "totalInventory": 0,
                                    "priceRangeV2": {"minVariantPrice": {"amount": "5.00"}},
                                    "metafield": None,
                                }
                            }
                        ]
                    }
                }
            }
        ]
    )

    products = client.get_products()

    assert products[0].cj_product_id == ""


def test_create_product_raises_on_productCreate_userErrors_without_calling_the_second_mutation():
    client, fake = _client(
        [{"data": {"productCreate": {"product": None, "userErrors": [{"field": ["title"], "message": "can't be blank"}]}}}]
    )

    with pytest.raises(RuntimeError, match="productCreate failed"):
        client.create_product(title="", description="d", price=10.0, images=[])

    assert len(fake.calls) == 1


def test_create_product_raises_on_productVariantsBulkCreate_userErrors():
    client, fake = _client(
        [
            {"data": {"productCreate": {"product": {"id": "gid://shopify/Product/1"}, "userErrors": []}}},
            {"data": {"productVariantsBulkCreate": {"productVariants": [], "userErrors": [{"field": ["price"], "message": "invalid"}]}}},
        ]
    )

    with pytest.raises(RuntimeError, match="productVariantsBulkCreate failed"):
        client.create_product(title="Widget", description="d", price=-5.0, images=[])


def test_execute_raises_on_a_top_level_graphql_errors_array():
    client, fake = _client([{"errors": [{"message": "Throttled"}]}])

    with pytest.raises(RuntimeError, match="Shopify GraphQL request error"):
        client._execute("query { shop { id } }", {})


def test_get_recent_orders_maps_the_real_response_shape_including_lowercasing_financial_status():
    client, fake = _client(
        [
            {
                "data": {
                    "orders": {
                        "edges": [
                            {
                                "node": {
                                    "id": "gid://shopify/Order/1",
                                    "displayFinancialStatus": "PAID",
                                    "totalPriceSet": {"shopMoney": {"amount": "29.99", "currencyCode": "USD"}},
                                    "lineItems": {
                                        "edges": [
                                            {
                                                "node": {
                                                    "id": "gid://shopify/LineItem/1",
                                                    "name": "Widget",
                                                    "quantity": 2,
                                                    "originalUnitPriceSet": {
                                                        "shopMoney": {"amount": "14.99", "currencyCode": "USD"}
                                                    },
                                                    "product": {
                                                        "metafield": {"value": "CJ-PRODUCT-1"},
                                                    },
                                                }
                                            }
                                        ]
                                    },
                                    "shippingAddress": {
                                        "name": "Jane Doe",
                                        "address1": "1 Main St",
                                        "city": "Springfield",
                                        "countryCodeV2": "US",
                                        "province": "Illinois",
                                        "zip": "62701",
                                        "phone": "+15551234567",
                                    },
                                }
                            },
                            {
                                "node": {
                                    "id": "gid://shopify/Order/2",
                                    "displayFinancialStatus": "PENDING",
                                    "totalPriceSet": {"shopMoney": {"amount": "5.00", "currencyCode": "USD"}},
                                    "lineItems": {"edges": []},
                                    "shippingAddress": None,
                                }
                            },
                        ]
                    }
                }
            }
        ]
    )

    orders = client.get_recent_orders()

    assert len(orders) == 2
    assert orders[0].order_id == "gid://shopify/Order/1"
    assert orders[0].financial_status == "paid"  # lowercased from "PAID"
    assert orders[0].total_price == 29.99
    assert orders[0].line_items == [
        {
            "id": "gid://shopify/LineItem/1",
            "name": "Widget",
            "quantity": 2,
            "price": "14.99",
            "cj_product_id": "CJ-PRODUCT-1",
        }
    ]
    assert orders[0].shipping_address == {
        "name": "Jane Doe",
        "address1": "1 Main St",
        "city": "Springfield",
        "country_code": "US",
        "province": "Illinois",
        "zip": "62701",
        "phone": "+15551234567",
    }
    # order 2 has no shippingAddress - must not crash, must come back empty
    assert orders[1].financial_status == "pending"
    assert orders[1].shipping_address == {}


def test_get_recent_orders_defaults_cj_product_id_to_empty_string_when_the_line_item_has_no_product():
    # A deleted product or a custom (non-catalog) line item has no "product"
    # reference at all - must not crash, must come back as "".
    client, fake = _client(
        [
            {
                "data": {
                    "orders": {
                        "edges": [
                            {
                                "node": {
                                    "id": "gid://shopify/Order/1",
                                    "displayFinancialStatus": "PAID",
                                    "totalPriceSet": {"shopMoney": {"amount": "5.00", "currencyCode": "USD"}},
                                    "lineItems": {
                                        "edges": [
                                            {
                                                "node": {
                                                    "id": "gid://shopify/LineItem/1",
                                                    "name": "Custom item",
                                                    "quantity": 1,
                                                    "originalUnitPriceSet": {
                                                        "shopMoney": {"amount": "5.00", "currencyCode": "USD"}
                                                    },
                                                    "product": None,
                                                }
                                            }
                                        ]
                                    },
                                    "shippingAddress": None,
                                }
                            }
                        ]
                    }
                }
            }
        ]
    )

    orders = client.get_recent_orders()

    assert orders[0].line_items[0]["cj_product_id"] == ""


def test_update_price_looks_up_the_first_variant_then_updates_its_price():
    client, fake = _client(
        [
            {"data": {"product": {"id": "gid://shopify/Product/1", "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/9"}]}}}},
            {"data": {"productVariantsBulkUpdate": {"product": {"id": "gid://shopify/Product/1"}, "productVariants": [{"id": "gid://shopify/ProductVariant/9", "price": "24.99"}], "userErrors": []}}},
        ]
    )

    client.update_price("gid://shopify/Product/1", 24.99)

    assert len(fake.calls) == 2
    lookup_query, lookup_vars = fake.calls[0]
    assert "GetProductFirstVariant" in lookup_query
    assert lookup_vars == {"id": "gid://shopify/Product/1"}

    update_query, update_vars = fake.calls[1]
    assert "productVariantsBulkUpdate" in update_query
    assert update_vars == {
        "productId": "gid://shopify/Product/1",
        "variantId": "gid://shopify/ProductVariant/9",
        "newPrice": "24.99",
    }


def test_update_price_raises_clearly_when_the_product_has_no_variant():
    client, fake = _client([{"data": {"product": {"id": "gid://shopify/Product/1", "variants": {"nodes": []}}}}])

    with pytest.raises(RuntimeError, match="no variant found"):
        client.update_price("gid://shopify/Product/1", 10.0)

    assert len(fake.calls) == 1  # never attempted the update without a variant id


def test_update_price_raises_on_productVariantsBulkUpdate_userErrors():
    client, fake = _client(
        [
            {"data": {"product": {"id": "gid://shopify/Product/1", "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/9"}]}}}},
            {"data": {"productVariantsBulkUpdate": {"product": None, "productVariants": [], "userErrors": [{"field": ["price"], "message": "invalid"}]}}},
        ]
    )

    with pytest.raises(RuntimeError, match="productVariantsBulkUpdate failed"):
        client.update_price("gid://shopify/Product/1", -5.0)


def test_update_tracking_looks_up_the_first_fulfillment_then_updates_its_tracking_info():
    client, fake = _client(
        [
            {"data": {"order": {"id": "gid://shopify/Order/1", "fulfillments": [{"id": "gid://shopify/Fulfillment/5"}]}}},
            {"data": {"fulfillmentTrackingInfoUpdate": {"fulfillment": {"id": "gid://shopify/Fulfillment/5"}, "userErrors": []}}},
        ]
    )

    client.update_tracking("gid://shopify/Order/1", "1Z001985YW99744790", "UPS")

    assert len(fake.calls) == 2
    lookup_query, lookup_vars = fake.calls[0]
    assert "OrderFulfillmentIds" in lookup_query
    assert lookup_vars == {"id": "gid://shopify/Order/1"}

    update_query, update_vars = fake.calls[1]
    assert "fulfillmentTrackingInfoUpdate" in update_query
    assert update_vars == {
        "fulfillmentId": "gid://shopify/Fulfillment/5",
        "trackingInfoInput": {"company": "UPS", "number": "1Z001985YW99744790"},
        "notifyCustomer": True,
    }


def test_update_tracking_raises_clearly_when_the_order_has_no_fulfillment():
    client, fake = _client([{"data": {"order": {"id": "gid://shopify/Order/1", "fulfillments": []}}}])

    with pytest.raises(RuntimeError, match="no fulfillment found"):
        client.update_tracking("gid://shopify/Order/1", "TRACK1", "DHL")

    assert len(fake.calls) == 1


def test_update_tracking_raises_on_fulfillmentTrackingInfoUpdate_userErrors():
    client, fake = _client(
        [
            {"data": {"order": {"id": "gid://shopify/Order/1", "fulfillments": [{"id": "gid://shopify/Fulfillment/5"}]}}},
            {"data": {"fulfillmentTrackingInfoUpdate": {"fulfillment": None, "userErrors": [{"field": ["trackingInfoInput"], "message": "invalid"}]}}},
        ]
    )

    with pytest.raises(RuntimeError, match="fulfillmentTrackingInfoUpdate failed"):
        client.update_tracking("gid://shopify/Order/1", "TRACK1", "DHL")
