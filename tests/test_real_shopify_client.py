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
    client = RealShopifyClient("test-shop.myshopify.com", "faketoken", "2024-07", "USD")
    fake = _FakeGraphQL(responses)
    client._shopify.GraphQL = lambda: fake
    return client, fake


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
    assert second_vars["variants"] == [{"price": {"amount": "19.99", "currencyCode": "USD"}}]


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
                                                }
                                            }
                                        ]
                                    },
                                    "shippingAddress": {
                                        "name": "Jane Doe",
                                        "address1": "1 Main St",
                                        "city": "Springfield",
                                        "countryCodeV2": "US",
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
        {"id": "gid://shopify/LineItem/1", "name": "Widget", "quantity": 2, "price": "14.99"}
    ]
    assert orders[0].shipping_address == {
        "name": "Jane Doe", "address1": "1 Main St", "city": "Springfield", "country_code": "US"
    }
    # order 2 has no shippingAddress - must not crash, must come back empty
    assert orders[1].financial_status == "pending"
    assert orders[1].shipping_address == {}


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
