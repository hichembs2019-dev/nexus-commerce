"""Unit tests for the one verified part of RealCJClient: the access-token
exchange. Verified 2026-10-11 - see docs/SOURCES.md "CJ Dropshipping >
Authentication". httpx.post is faked here since it needs a real CJ account;
everything above that call is real project code. Every data method
(search_products, get_shipping_cost, get_product, create_order,
track_shipment) is still unverified and still raises NotImplementedError -
not covered here, same as before.
"""
from __future__ import annotations

import pytest

from src.integrations.cj_client import CJProduct, RealCJClient


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_get_access_token_posts_the_api_key_and_returns_the_access_token(monkeypatch):
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append((url, json, headers))
        return _FakeResponse(
            {
                "code": 200,
                "result": True,
                "message": "Success",
                "data": {"openId": 1, "accessToken": "real-token-123", "refreshToken": "r"},
                "success": True,
            }
        )

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    token = client._get_access_token()

    assert token == "real-token-123"
    assert len(calls) == 1
    url, body, headers = calls[0]
    assert url == "https://developers.cjdropshipping.com/api2.0/v1/authentication/getAccessToken"
    assert body == {"apiKey": "fake-cj-api-key"}
    assert headers == {"Content-Type": "application/json"}


def test_get_access_token_is_cached_and_not_refetched(monkeypatch):
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    call_count = 0

    def fake_post(url, *, json, headers, timeout):
        nonlocal call_count
        call_count += 1
        return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    client._get_access_token()
    client._get_access_token()

    assert call_count == 1


def test_get_access_token_raises_clearly_on_authentication_failure(monkeypatch):
    client = RealCJClient("bad-key", "https://developers.cjdropshipping.com/api2.0/v1")

    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse({"code": 1600001, "result": False, "message": "Authentication failed"})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(RuntimeError, match="CJ authentication failed"):
        client._get_access_token()


def test_search_products_sends_the_keyword_and_maps_the_real_response_shape(monkeypatch):
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})

    calls = []

    def fake_get(url, *, params, headers, timeout):
        calls.append((url, params, headers))
        return _FakeResponse(
            {
                "code": 200,
                "result": True,
                "data": {
                    "content": [
                        {
                            "productList": [
                                {"id": "P1", "nameEn": "Hoodie", "sku": "SKU1", "sellPrice": "11.85"},
                                {"id": "P2", "nameEn": "T-Shirt", "sku": "SKU2", "sellPrice": "5.00"},
                            ],
                            "keyWord": "hoodie",
                        }
                    ]
                },
            }
        )

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)

    products = client.search_products("hoodie")

    assert len(calls) == 1
    url, params, headers = calls[0]
    assert url == "https://developers.cjdropshipping.com/api2.0/v1/product/listV2"
    assert params == {"keyWord": "hoodie"}
    assert headers == {"CJ-Access-Token": "tok"}

    assert products == [
        CJProduct(product_id="P1", title="Hoodie", price=11.85),
        CJProduct(product_id="P2", title="T-Shirt", price=5.00),
    ]


def test_search_products_raises_clearly_on_failure(monkeypatch):
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})

    def fake_get(url, *, params, headers, timeout):
        return _FakeResponse({"code": 1600100, "result": False, "message": "Param error"})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(RuntimeError, match="CJ product search failed"):
        client.search_products("hoodie")
