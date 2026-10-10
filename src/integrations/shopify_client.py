"""Verified usage: docs/SOURCES.md "Shopify (ShopifyAPI Python package)".
The session/authentication setup below is real and verified. The actual
GraphQL query/mutation bodies are NOT verified (docs/UNVERIFIED.md) -
shopify.dev was unreachable this session - so every data-fetching/mutating
method on RealShopifyClient raises NotImplementedError rather than guessing
field names Shopify is known to rename across API versions.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ShopifyOrder:
    order_id: str
    financial_status: str
    total_price: float
    line_items: list[dict] = field(default_factory=list)
    shipping_address: dict = field(default_factory=dict)


@dataclass
class ShopifyProduct:
    product_id: str
    title: str
    price: float
    inventory: int
    # No such mapping exists in the spec's data model - this project stores
    # it directly on the product (set when the product is first published;
    # see new_product_discovery.py) rather than inventing a separate mapping
    # table for a single foreign-key column.
    cj_product_id: str = ""


class ShopifyClient(ABC):
    @abstractmethod
    def get_recent_orders(self) -> list[ShopifyOrder]:
        """Orders to check for financial_status == 'paid' (spec SS4 #5)."""

    @abstractmethod
    def create_product(
        self, *, title: str, description: str, price: float, images: list[str], cj_product_id: str = ""
    ) -> str:
        """Returns the new product's id."""

    @abstractmethod
    def get_products(self) -> list[ShopifyProduct]:
        """For the hourly price/inventory review workflow."""

    @abstractmethod
    def update_price(self, product_id: str, new_price: float) -> None: ...

    @abstractmethod
    def update_tracking(self, order_id: str, tracking_number: str, carrier: str) -> None: ...


class RealShopifyClient(ShopifyClient):
    """Session setup is the one part of this class that's actually verified
    - see the module docstring. A NotImplementedError from any other method
    is not a bug to patch around; it's spec SS... the project's own
    verification rule, doing exactly what it says: "إن لم تستطع التحقق من
    شيء... لا تستخدمه."
    """

    _UNVERIFIED = (
        "Shopify GraphQL query/mutation body not verified this session "
        "(shopify.dev was blocked by this sandbox's egress policy) - see "
        "docs/UNVERIFIED.md. Fill this in once it can be confirmed."
    )

    def __init__(self, shop_url: str, access_token: str, api_version: str):
        import shopify

        self._shopify = shopify
        session = shopify.Session(shop_url, api_version, access_token)
        shopify.ShopifyResource.activate_session(session)

    def get_recent_orders(self) -> list[ShopifyOrder]:
        raise NotImplementedError(self._UNVERIFIED)

    def create_product(
        self, *, title: str, description: str, price: float, images: list[str], cj_product_id: str = ""
    ) -> str:
        raise NotImplementedError(self._UNVERIFIED)

    def get_products(self) -> list[ShopifyProduct]:
        raise NotImplementedError(self._UNVERIFIED)

    def update_price(self, product_id: str, new_price: float) -> None:
        raise NotImplementedError(self._UNVERIFIED)

    def update_tracking(self, order_id: str, tracking_number: str, carrier: str) -> None:
        raise NotImplementedError(self._UNVERIFIED)


class MockShopifyClient(ShopifyClient):
    """Fully functional in-memory fake - what every test and every DRY_RUN
    run actually exercises. Seed `.orders` / `.products` directly in tests.
    """

    def __init__(self):
        self.orders: list[ShopifyOrder] = []
        self.products: list[ShopifyProduct] = []
        self._next_product_id = 1
        self.price_updates: list[tuple[str, float]] = []
        self.tracking_updates: list[tuple[str, str, str]] = []

    def get_recent_orders(self) -> list[ShopifyOrder]:
        return list(self.orders)

    def create_product(
        self, *, title: str, description: str, price: float, images: list[str], cj_product_id: str = ""
    ) -> str:
        product_id = f"mock-product-{self._next_product_id}"
        self._next_product_id += 1
        self.products.append(
            ShopifyProduct(
                product_id=product_id, title=title, price=price, inventory=0, cj_product_id=cj_product_id
            )
        )
        return product_id

    def get_products(self) -> list[ShopifyProduct]:
        return list(self.products)

    def update_price(self, product_id: str, new_price: float) -> None:
        self.price_updates.append((product_id, new_price))
        for p in self.products:
            if p.product_id == product_id:
                p.price = new_price

    def update_tracking(self, order_id: str, tracking_number: str, carrier: str) -> None:
        self.tracking_updates.append((order_id, tracking_number, carrier))
