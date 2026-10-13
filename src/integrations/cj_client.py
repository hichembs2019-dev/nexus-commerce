"""CJ Dropshipping - most of the API surface is still unverified (see
docs/UNVERIFIED.md). Method names below are this project's own domain
vocabulary, not CJ's own API vocabulary. Authentication is now verified and
real - see docs/SOURCES.md "CJ Dropshipping > Authentication", read by the
owner directly from developers.cjdropshipping.com (blocked from this
project's own dev session, reachable from the owner's device) on
2026-10-11.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CJProduct:
    product_id: str
    title: str
    price: float
    # "bigImage" in the real listV2 response (docs/SOURCES.md "Product
    # search") - was documented from the start but never mapped onto this
    # dataclass, so every real new-product proposal's `images` list stayed
    # empty. Found live 2026-10-13: the 5 agents correctly rejected a real
    # candidate for exactly that reason ("can't publish without images").
    image_url: str = ""


@dataclass
class TrackingInfo:
    status: str
    tracking_number: str
    carrier: str = ""


class CJClient(ABC):
    @abstractmethod
    def search_products(self, query: str) -> list[CJProduct]: ...

    @abstractmethod
    def get_shipping_cost(self, product_id: str, country: str) -> float: ...

    @abstractmethod
    def get_product(self, product_id: str) -> CJProduct:
        """For the price/inventory review workflow - this supplier's
        current price for a product already listed in the store.
        """

    @abstractmethod
    def create_order(self, *, product_id: str, quantity: int, shipping_address: dict) -> str:
        """Returns CJ's order id."""

    @abstractmethod
    def track_shipment(self, cj_order_id: str) -> TrackingInfo: ...


def _parse_cj_price(raw: str | float | int) -> float:
    """CJ's "sellPrice" comes back as a plain number in some responses
    (confirmed live via get_product) but as a "low -- high" range STRING
    (e.g. "2.13 -- 7.21") in others, for a product with several variants at
    different prices - found live on 2026-10-12 when a real search crashed
    on `float("2.13 -- 7.21")`. A range takes the HIGH end: this value feeds
    margin checks, and the owner's own standing instruction is that a
    purchase must never turn into a loss - so cost estimates must never be
    optimistic. The exact per-variant price is looked up for real before any
    order is placed (get_shipping_cost / create_order take a specific
    product_id, not this aggregate figure).
    """
    if isinstance(raw, str) and "--" in raw:
        _, high = raw.split("--")
        return float(high.strip())
    return float(raw)


class RealCJClient(CJClient):
    """Every method is now verified and implemented - see the module
    docstring and docs/SOURCES.md "CJ Dropshipping" for the full exchange,
    including every explicitly-flagged assumption (product_id vs variant
    id, shippingProvince's missing source, orderNumber's local generation -
    see docs/UNVERIFIED.md).
    """

    _UNVERIFIED = "CJ Dropshipping API not verified this session - see docs/UNVERIFIED.md"

    def __init__(self, api_key: str, base_url: str):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._access_token: str | None = None

    def _get_access_token(self) -> str:
        # Verified 2026-10-11 - see docs/SOURCES.md "CJ Dropshipping >
        # Authentication". CJ caches the token server-side for 24h per
        # account, so re-fetching per client instance is cheap, not wasteful.
        if self._access_token is None:
            import httpx

            response = httpx.post(
                f"{self._base_url}/authentication/getAccessToken",
                json={"apiKey": self._api_key},
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            payload = response.json()
            if not payload.get("result"):
                raise RuntimeError(f"CJ authentication failed: {payload.get('message')}")
            self._access_token = payload["data"]["accessToken"]
        return self._access_token

    def search_products(self, query: str) -> list[CJProduct]:
        # Verified 2026-10-12 - see docs/SOURCES.md "CJ Dropshipping >
        # Product search". Uses listV2 (elasticsearch-backed, supports
        # keyword search), not the deprecated listV1.
        import httpx

        response = httpx.get(
            f"{self._base_url}/product/listV2",
            params={"keyWord": query},
            headers={"CJ-Access-Token": self._get_access_token()},
            timeout=30,
        )
        payload = response.json()
        if not payload.get("result"):
            raise RuntimeError(f"CJ product search failed: {payload.get('message')}")

        products: list[CJProduct] = []
        for block in payload["data"]["content"]:
            for item in block.get("productList", []):
                products.append(
                    CJProduct(
                        product_id=item["id"],
                        title=item["nameEn"],
                        price=_parse_cj_price(item["sellPrice"]),
                        image_url=item.get("bigImage", ""),
                    )
                )
        return products

    def get_shipping_cost(self, product_id: str, country: str) -> float:
        # Verified 2026-10-12 - see docs/SOURCES.md "CJ Dropshipping >
        # Shipping cost". "CN" origin and "first option" are this project's
        # own simple defaults, not CJ's. product_id is passed as "vid"
        # (variant id) - unconfirmed assumption, flagged in SOURCES.md.
        import httpx

        response = httpx.post(
            f"{self._base_url}/logistic/freightCalculate",
            json={
                "startCountryCode": "CN",
                "endCountryCode": country,
                "products": [{"quantity": 1, "vid": product_id}],
            },
            headers={"CJ-Access-Token": self._get_access_token(), "Content-Type": "application/json"},
            timeout=30,
        )
        payload = response.json()
        if not payload.get("result"):
            raise RuntimeError(f"CJ freight calculation failed: {payload.get('message')}")

        options = payload["data"]
        if not options:
            raise RuntimeError(f"no shipping options returned for product {product_id} to {country}")
        return float(options[0]["logisticPrice"])

    def get_product(self, product_id: str) -> CJProduct:
        # Verified 2026-10-12 - see docs/SOURCES.md "CJ Dropshipping >
        # Product details". Field is "productNameEn" here, not "nameEn" as
        # in search_products()'s listV2 response - confirmed, not assumed
        # to match.
        import httpx

        response = httpx.get(
            f"{self._base_url}/product/query",
            params={"pid": product_id},
            headers={"CJ-Access-Token": self._get_access_token()},
            timeout=30,
        )
        payload = response.json()
        if not payload.get("result"):
            raise RuntimeError(f"CJ product query failed: {payload.get('message')}")

        data = payload["data"]
        return CJProduct(product_id=data["pid"], title=data["productNameEn"], price=_parse_cj_price(data["sellPrice"]))

    def create_order(self, *, product_id: str, quantity: int, shipping_address: dict) -> str:
        # Verified 2026-10-12 - see docs/SOURCES.md "CJ Dropshipping >
        # Create order" for the three gaps flagged here: product_id passed
        # as "vid" (unconfirmed), shippingProvince has no real source in
        # this project's Shopify order data, and orderNumber is generated
        # locally since this method's signature carries no order reference.
        import uuid

        import httpx

        order_number = shipping_address.get("order_number") or str(uuid.uuid4())
        payload = {
            "orderNumber": order_number,
            "shippingCountryCode": shipping_address.get("country_code", ""),
            "shippingCountry": shipping_address.get("country_code", ""),
            "shippingProvince": shipping_address.get("province", ""),
            "shippingCity": shipping_address.get("city", ""),
            "shippingCustomerName": shipping_address.get("name", ""),
            "shippingAddress": shipping_address.get("address1", ""),
            "shippingZip": shipping_address.get("zip", ""),
            "shippingPhone": shipping_address.get("phone", ""),
            "fromCountryCode": "CN",
            "platform": "shopify",
            "products": [{"vid": product_id, "quantity": quantity}],
        }

        response = httpx.post(
            f"{self._base_url}/shopping/order/createOrderV3",
            json=payload,
            headers={"CJ-Access-Token": self._get_access_token(), "Content-Type": "application/json"},
            timeout=30,
        )
        result = response.json()
        if not result.get("result"):
            raise RuntimeError(f"CJ order creation failed: {result.get('message')}")

        data = result["data"]
        if data.get("interceptOrderReasons"):
            raise RuntimeError(f"CJ order creation intercepted: {data['interceptOrderReasons']}")

        return data["orderId"]

    def track_shipment(self, cj_order_id: str) -> TrackingInfo:
        # Verified 2026-10-12 - see docs/SOURCES.md "CJ Dropshipping >
        # Track shipment". Two real steps: order detail (for trackNumber,
        # null until CJ ships it - a normal state, not an error) then the
        # carrier tracking lookup already verified for logistic/trackInfo.
        import httpx

        order_response = httpx.get(
            f"{self._base_url}/shopping/order/getOrderDetail",
            params={"orderId": cj_order_id},
            headers={"CJ-Access-Token": self._get_access_token()},
            timeout=30,
        )
        order_payload = order_response.json()
        if not order_payload.get("result"):
            raise RuntimeError(f"CJ order query failed: {order_payload.get('message')}")

        order_data = order_payload["data"]
        track_number = order_data.get("trackNumber")
        if not track_number:
            return TrackingInfo(
                status=order_data.get("orderStatus", ""), tracking_number="", carrier=order_data.get("logisticName", "")
            )

        tracking_response = httpx.get(
            f"{self._base_url}/logistic/trackInfo",
            params={"trackNumber": track_number},
            headers={"CJ-Access-Token": self._get_access_token()},
            timeout=30,
        )
        tracking_payload = tracking_response.json()
        if not tracking_payload.get("result"):
            raise RuntimeError(f"CJ tracking query failed: {tracking_payload.get('message')}")

        entries = tracking_payload["data"]
        if not entries:
            return TrackingInfo(
                status=order_data.get("orderStatus", ""),
                tracking_number=track_number,
                carrier=order_data.get("logisticName", ""),
            )

        entry = entries[0]
        return TrackingInfo(
            status=entry.get("trackingStatus", ""),
            tracking_number=entry.get("trackingNumber", track_number),
            carrier=entry.get("lastMileCarrier", ""),
        )


class MockCJClient(CJClient):
    """Fully functional in-memory fake - what every test and every DRY_RUN
    run actually exercises."""

    def __init__(self):
        self.catalog: list[CJProduct] = []
        self.shipping_costs: dict[tuple[str, str], float] = {}
        self.orders: dict[str, dict] = {}
        self.tracking: dict[str, TrackingInfo] = {}
        self._next_order_id = 1

    def search_products(self, query: str) -> list[CJProduct]:
        return [p for p in self.catalog if query.lower() in p.title.lower()]

    def get_shipping_cost(self, product_id: str, country: str) -> float:
        return self.shipping_costs.get((product_id, country), 0.0)

    def get_product(self, product_id: str) -> CJProduct:
        for p in self.catalog:
            if p.product_id == product_id:
                return p
        raise KeyError(f"no such CJ product: {product_id}")

    def create_order(self, *, product_id: str, quantity: int, shipping_address: dict) -> str:
        cj_order_id = f"mock-cj-order-{self._next_order_id}"
        self._next_order_id += 1
        self.orders[cj_order_id] = {
            "product_id": product_id,
            "quantity": quantity,
            "shipping_address": shipping_address,
        }
        self.tracking[cj_order_id] = TrackingInfo(status="processing", tracking_number="")
        return cj_order_id

    def track_shipment(self, cj_order_id: str) -> TrackingInfo:
        if cj_order_id not in self.tracking:
            raise KeyError(f"no such CJ order: {cj_order_id}")
        return self.tracking[cj_order_id]

    def set_tracking(self, cj_order_id: str, info: TrackingInfo) -> None:
        """Test helper - simulates CJ updating a shipment's status."""
        self.tracking[cj_order_id] = info
