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


class RealCJClient(CJClient):
    """Authentication (__init__ / _access_token) is real and verified - see
    the module docstring. Every data method still raises - see
    docs/UNVERIFIED.md. Nothing about CJ's product/order/tracking endpoints
    was confirmed against any reachable source this session, so nothing is
    guessed here.
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
        raise NotImplementedError(self._UNVERIFIED)

    def get_shipping_cost(self, product_id: str, country: str) -> float:
        raise NotImplementedError(self._UNVERIFIED)

    def get_product(self, product_id: str) -> CJProduct:
        raise NotImplementedError(self._UNVERIFIED)

    def create_order(self, *, product_id: str, quantity: int, shipping_address: dict) -> str:
        raise NotImplementedError(self._UNVERIFIED)

    def track_shipment(self, cj_order_id: str) -> TrackingInfo:
        raise NotImplementedError(self._UNVERIFIED)


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
