"""Unit tests for the one verified part of RealShopifyClient: create_product()
(productCreate + productVariantsBulkCreate). Verified 2026-10-11 - see
docs/SOURCES.md "productCreate with images" / "productVariantsBulkCreate
(price)". shopify.GraphQL().execute() is faked here since it needs a real
Shopify session; everything above that call is real project code.
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
