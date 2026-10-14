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

from src.integrations.cj_client import CJProduct, RealCJClient, TrackingInfo


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

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


def test_search_products_maps_bigImage_to_image_url(monkeypatch):
    # Found live 2026-10-13: bigImage was documented from the start
    # (docs/SOURCES.md "Product search") but never mapped onto CJProduct,
    # so every real new-product proposal's images list stayed empty and
    # the 5 agents correctly rejected it for that reason.
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})

    def fake_get(url, *, params, headers, timeout):
        return _FakeResponse(
            {
                "code": 200,
                "result": True,
                "data": {
                    "content": [
                        {
                            "productList": [
                                {
                                    "id": "P1",
                                    "nameEn": "Hoodie",
                                    "sellPrice": "11.85",
                                    "bigImage": "https://cc-west-usa.oss-example/hoodie.jpg",
                                },
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

    assert products == [
        CJProduct(
            product_id="P1",
            title="Hoodie",
            price=11.85,
            image_url="https://cc-west-usa.oss-example/hoodie.jpg",
        )
    ]


def test_search_products_parses_a_price_range_sellprice_using_the_high_end(monkeypatch):
    # Found live on 2026-10-12: a real CJ search returned sellPrice
    # "2.13 -- 7.21" for a multi-variant product and float() crashed on it.
    # The high end is used deliberately (see _parse_cj_price's docstring) so
    # margin checks never under-estimate cost.
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})

    def fake_get(url, *, params, headers, timeout):
        return _FakeResponse(
            {
                "code": 200,
                "result": True,
                "data": {
                    "content": [
                        {
                            "productList": [
                                {"id": "P1", "nameEn": "Multi-variant hoodie", "sku": "SKU1", "sellPrice": "2.13 -- 7.21"},
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

    assert products == [CJProduct(product_id="P1", title="Multi-variant hoodie", price=7.21)]


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


def test_get_product_sends_pid_and_maps_the_real_response_shape(monkeypatch):
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
                    "pid": "000B9312-456A-4D31-94BD-B083E2A198E8",
                    "productNameEn": "Small trailer model",
                    "sellPrice": 58.09,
                },
            }
        )

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)

    product = client.get_product("000B9312-456A-4D31-94BD-B083E2A198E8")

    assert len(calls) == 1
    url, params, headers = calls[0]
    assert url == "https://developers.cjdropshipping.com/api2.0/v1/product/query"
    assert params == {"pid": "000B9312-456A-4D31-94BD-B083E2A198E8"}
    assert headers == {"CJ-Access-Token": "tok"}

    assert product == CJProduct(
        product_id="000B9312-456A-4D31-94BD-B083E2A198E8", title="Small trailer model", price=58.09
    )


def test_get_product_parses_a_price_range_sellprice_using_the_high_end(monkeypatch):
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})

    def fake_get(url, *, params, headers, timeout):
        return _FakeResponse(
            {
                "code": 200,
                "result": True,
                "data": {"pid": "P1", "productNameEn": "Multi-variant hoodie", "sellPrice": "2.13 -- 7.21"},
            }
        )

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)

    product = client.get_product("P1")

    assert product == CJProduct(product_id="P1", title="Multi-variant hoodie", price=7.21)


def test_get_product_parses_a_single_dash_no_spaces_price_range_too(monkeypatch):
    # Found live 2026-10-14 on the real production server: CJ's range
    # separator isn't always "--" with spaces - this one real response was
    # "12.67-22.83" (one dash, no spaces), which crashed with
    # `ValueError: could not convert string to float: '12.67-22.83'` every
    # hourly price-review cycle.
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})

    def fake_get(url, *, params, headers, timeout):
        return _FakeResponse(
            {
                "code": 200,
                "result": True,
                "data": {"pid": "P1", "productNameEn": "Multi-variant hoodie", "sellPrice": "12.67-22.83"},
            }
        )

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)

    product = client.get_product("P1")

    assert product == CJProduct(product_id="P1", title="Multi-variant hoodie", price=22.83)


def test_get_product_raises_clearly_on_failure(monkeypatch):
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})

    def fake_get(url, *, params, headers, timeout):
        return _FakeResponse({"code": 1600100, "result": False, "message": "Param error"})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(RuntimeError, match="CJ product query failed"):
        client.get_product("missing")


def _fake_get_with_variants(vid: str):
    def fake_get(url, *, params, headers, timeout):
        return _FakeResponse(
            {
                "code": 200,
                "result": True,
                "data": {
                    "pid": params["pid"],
                    "productNameEn": "Phone Case",
                    "sellPrice": 5.0,
                    "variants": [{"vid": vid}],
                },
            }
        )

    return fake_get


def test_get_shipping_cost_resolves_the_real_vid_from_product_query_not_the_pid(monkeypatch):
    # Found live 2026-10-13: "pid" (search/listing id) and "vid" (variant
    # id) are NOT interchangeable - passing a real pid as vid to
    # freightCalculate returned a real, live "Variant not found" error.
    # A real vid only comes from product/query's data.variants[].vid.
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    def fake_post_auth(url, *, json, headers, timeout):
        if url.endswith("/authentication/getAccessToken"):
            return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})
        return _FakeResponse(
            {
                "code": 200,
                "result": True,
                "data": [
                    {"logisticAging": "2-5", "logisticPrice": 4.71, "logisticPriceCn": 30.54, "logisticName": "USPS+"},
                    {"logisticAging": "5-10", "logisticPrice": 2.00, "logisticPriceCn": 14.0, "logisticName": "Cheap Slow"},
                ],
            }
        )

    calls = []

    def fake_post(url, *, json=None, headers, timeout):
        calls.append((url, json, headers))
        return fake_post_auth(url, json=json, headers=headers, timeout=timeout)

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", _fake_get_with_variants("REAL-VID-999"))

    cost = client.get_shipping_cost("P1", "US")

    assert cost == 4.71  # first option, not the cheapest - a documented simple default
    freight_call = calls[-1]
    url, body, headers = freight_call
    assert url == "https://developers.cjdropshipping.com/api2.0/v1/logistic/freightCalculate"
    assert body == {
        "startCountryCode": "CN",
        "endCountryCode": "US",
        "products": [{"quantity": 1, "vid": "REAL-VID-999"}],  # the resolved vid, never the pid "P1"
    }
    assert headers["CJ-Access-Token"] == "tok"


def test_get_shipping_cost_retries_once_on_429_then_succeeds(monkeypatch):
    # Found live 2026-10-13: CJ's freightCalculate enforces "QPS limit is 1
    # time/1 second" and returns a real HTTP 429 under load.
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    attempts = {"n": 0}

    def fake_post(url, *, json=None, headers, timeout):
        if url.endswith("/authentication/getAccessToken"):
            return _FakeResponse({"result": True, "data": {"accessToken": "tok"}}, 200)
        attempts["n"] += 1
        if attempts["n"] == 1:
            return _FakeResponse(
                {"code": 1600200, "result": False, "message": "Too Many Requests, QPS limit is 1 time/1second"}, 429
            )
        return _FakeResponse({"code": 200, "result": True, "data": [{"logisticPrice": 4.71}]}, 200)

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", _fake_get_with_variants("REAL-VID-999"))
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)

    cost = client.get_shipping_cost("P1", "US")

    assert cost == 4.71
    assert attempts["n"] == 2  # first 429, then a real retry - not a crash


def test_get_shipping_cost_raises_clearly_when_no_options_are_returned(monkeypatch):
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    def fake_post(url, *, json=None, headers, timeout):
        if url.endswith("/authentication/getAccessToken"):
            return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})
        return _FakeResponse({"code": 200, "result": True, "data": []})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", _fake_get_with_variants("REAL-VID-999"))

    with pytest.raises(RuntimeError, match="no shipping options"):
        client.get_shipping_cost("P1", "US")


def test_get_shipping_cost_raises_clearly_on_failure(monkeypatch):
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    def fake_post(url, *, json=None, headers, timeout):
        if url.endswith("/authentication/getAccessToken"):
            return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})
        return _FakeResponse({"code": 1600300, "result": False, "message": "weight is required"})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", _fake_get_with_variants("REAL-VID-999"))

    with pytest.raises(RuntimeError, match="CJ freight calculation failed"):
        client.get_shipping_cost("P1", "US")


def test_create_order_resolves_the_real_vid_from_product_query_not_the_pid(monkeypatch):
    # Same real bug as freightCalculate: createOrderV3 also takes a real
    # "vid", never the "pid" passed in by the caller.
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    calls = []

    def fake_post(url, *, json, headers, timeout):
        if url.endswith("/authentication/getAccessToken"):
            return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})
        calls.append((url, json, headers))
        return _FakeResponse(
            {
                "code": 200,
                "result": True,
                "data": {"orderId": "CJ123456", "orderStatus": "CREATED", "interceptOrderReasons": []},
            }
        )

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", _fake_get_with_variants("REAL-VID-999"))

    order_id = client.create_order(product_id="P1", quantity=2, shipping_address={"name": "Jane Doe"})

    assert order_id == "CJ123456"
    assert calls[0][1]["products"] == [{"vid": "REAL-VID-999", "quantity": 2}]  # resolved vid, never "P1"


def test_create_order_sends_mapped_fields_and_returns_the_cj_order_id(monkeypatch):
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    calls = []

    def fake_post(url, *, json, headers, timeout):
        if url.endswith("/authentication/getAccessToken"):
            return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})
        calls.append((url, json, headers))
        return _FakeResponse(
            {
                "code": 200,
                "result": True,
                "data": {"orderId": "CJ123456", "orderStatus": "CREATED", "interceptOrderReasons": []},
            }
        )

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", _fake_get_with_variants("REAL-VID-999"))

    order_id = client.create_order(
        product_id="P1",
        quantity=2,
        shipping_address={
            "name": "Jane Doe",
            "address1": "1 Main St",
            "city": "Springfield",
            "country_code": "US",
            "province": "IL",
            "zip": "62701",
            "phone": "5551234",
        },
    )

    assert order_id == "CJ123456"
    url, body, headers = calls[0]
    assert url == "https://developers.cjdropshipping.com/api2.0/v1/shopping/order/createOrderV3"
    assert body["shippingCustomerName"] == "Jane Doe"
    assert body["shippingAddress"] == "1 Main St"
    assert body["shippingCity"] == "Springfield"
    assert body["shippingCountryCode"] == "US"
    assert body["shippingProvince"] == "IL"
    assert body["products"] == [{"vid": "REAL-VID-999", "quantity": 2}]
    assert headers["CJ-Access-Token"] == "tok"


def test_create_order_raises_on_intercept_reasons_even_when_result_is_true(monkeypatch):
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    def fake_post(url, *, json, headers, timeout):
        if url.endswith("/authentication/getAccessToken"):
            return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})
        return _FakeResponse(
            {
                "code": 200,
                "result": True,
                "data": {"orderId": None, "interceptOrderReasons": [{"code": 1001, "message": "stock issue"}]},
            }
        )

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", _fake_get_with_variants("REAL-VID-999"))

    with pytest.raises(RuntimeError, match="CJ order creation intercepted"):
        client.create_order(product_id="P1", quantity=1, shipping_address={})


def test_create_order_raises_clearly_on_failure(monkeypatch):
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    def fake_post(url, *, json, headers, timeout):
        if url.endswith("/authentication/getAccessToken"):
            return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})
        return _FakeResponse({"code": 1600300, "result": False, "message": "shippingProvince is required"})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", _fake_get_with_variants("REAL-VID-999"))

    with pytest.raises(RuntimeError, match="CJ order creation failed"):
        client.create_order(product_id="P1", quantity=1, shipping_address={})


def test_track_shipment_looks_up_order_detail_then_the_carrier_tracking_info(monkeypatch):
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    calls = []

    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})

    def fake_get(url, *, params, headers, timeout):
        calls.append((url, params))
        if url.endswith("/shopping/order/getOrderDetail"):
            return _FakeResponse(
                {
                    "code": 200,
                    "result": True,
                    "data": {"orderId": "CJ1", "orderStatus": "SHIPPED", "logisticName": "CJPacket Ordinary", "trackNumber": "CJPKL123"},
                }
            )
        return _FakeResponse(
            {
                "code": 200,
                "result": True,
                "data": [
                    {
                        "trackingNumber": "CJPKL123",
                        "trackingStatus": "In transit",
                        "lastMileCarrier": "CJPacket",
                    }
                ],
            }
        )

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)

    info = client.track_shipment("CJ1")

    assert info == TrackingInfo(status="In transit", tracking_number="CJPKL123", carrier="CJPacket")
    assert len(calls) == 2
    assert calls[0][0] == "https://developers.cjdropshipping.com/api2.0/v1/shopping/order/getOrderDetail"
    assert calls[0][1] == {"orderId": "CJ1"}
    assert calls[1][0] == "https://developers.cjdropshipping.com/api2.0/v1/logistic/trackInfo"
    assert calls[1][1] == {"trackNumber": "CJPKL123"}


def test_track_shipment_returns_order_status_when_not_yet_shipped_without_calling_trackinfo(monkeypatch):
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})

    calls = []

    def fake_get(url, *, params, headers, timeout):
        calls.append(url)
        return _FakeResponse(
            {"code": 200, "result": True, "data": {"orderId": "CJ1", "orderStatus": "PROCESSING", "logisticName": "CJPacket Ordinary", "trackNumber": None}}
        )

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)

    info = client.track_shipment("CJ1")

    assert info == TrackingInfo(status="PROCESSING", tracking_number="", carrier="CJPacket Ordinary")
    assert len(calls) == 1  # never called trackInfo with no tracking number yet


def test_track_shipment_raises_clearly_on_order_lookup_failure(monkeypatch):
    client = RealCJClient("fake-cj-api-key", "https://developers.cjdropshipping.com/api2.0/v1")

    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse({"result": True, "data": {"accessToken": "tok"}})

    def fake_get(url, *, params, headers, timeout):
        return _FakeResponse({"code": 1600300, "result": False, "message": "order not found"})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(RuntimeError, match="CJ order query failed"):
        client.track_shipment("missing")
