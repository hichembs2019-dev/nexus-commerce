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

from src.integrations.cj_client import RealCJClient


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
