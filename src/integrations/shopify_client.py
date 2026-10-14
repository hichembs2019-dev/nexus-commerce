"""Verified usage: docs/SOURCES.md "Shopify". Authentication uses the
Client credentials grant (verified 2026-10-12, see docs/SOURCES.md
"Shopify > Client credentials access token") - the flow Shopify's own docs
name for "apps that act only on stores in your own organization", which is
exactly this project's case (a custom app for the owner's own store, no
merchant-install step). The app exchanges its Client ID + Client Secret for
a short-lived (~24h) access token itself, the same way RealCJClient
exchanges its API Key for a CJ access token - no manually-obtained static
token, no OAuth redirect.
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

    Every method is now verified and implemented - live, on 2026-10-11, via
    shopify.dev's own "Ask assistant", from the owner's own device
    (shopify.dev is blocked from this project's dev session - see
    docs/SOURCES.md for the full exchange, with source citations where the
    tool gave them).
    """

    _UNVERIFIED = (
        "Shopify GraphQL query/mutation body not verified this session "
        "(shopify.dev was blocked by this sandbox's egress policy) - see "
        "docs/UNVERIFIED.md. Fill this in once it can be confirmed."
    )

    # productCreate (title/description/media) + productVariantsBulkCreate
    # (price) are two separate mutations - see docs/SOURCES.md. Price lives
    # on the variant, not the product. Verified live 2026-10-13:
    # ProductVariantsBulkInput.price is a bare decimal string (e.g. "9.99"),
    # not a {amount, currencyCode} object - Shopify rejected the object
    # shape as "invalid money" - so the amount is simply interpreted in
    # whatever currency the store itself is configured with. There was
    # never a real currency_code setting to wire in here; the one that used
    # to exist on this class was dead code (stored, never read) and has
    # been removed.
    _PRODUCT_CREATE = """
    mutation ProductCreateWithImages($title: String!, $descriptionHtml: String, $media: [CreateMediaInput!], $metafields: [MetafieldInput!]) {
      productCreate(
        product: { title: $title, descriptionHtml: $descriptionHtml, metafields: $metafields }
        media: $media
      ) {
        product { id }
        userErrors { field message }
      }
    }
    """

    # Verified 2026-10-13 - see docs/SOURCES.md "Product metafield for
    # cj_product_id". Namespace is this project's own ("nexus_commerce"),
    # not a Shopify-reserved one - confirmed the "namespace" argument on
    # both productCreate's MetafieldInput and Product.metafield() is a
    # plain app-chosen string, not a fixed value.
    _CJ_PRODUCT_ID_NAMESPACE = "nexus_commerce"
    _CJ_PRODUCT_ID_KEY = "cj_product_id"

    # Verified 2026-10-13 - see docs/SOURCES.md "Products list query".
    _LIST_PRODUCTS = """
    query ListProducts($first: Int = 50) {
      products(first: $first) {
        edges {
          node {
            id
            title
            totalInventory
            priceRangeV2 { minVariantPrice { amount } }
            metafield(namespace: "nexus_commerce", key: "cj_product_id") { value }
          }
        }
      }
    }
    """

    # Verified 2026-10-13 - see docs/SOURCES.md "productVariantsBulkCreate
    # strategy". Explicit REMOVE_STANDALONE_VARIANT, not the field's own
    # DEFAULT, because a live call on API version 2024-07 hit "The variant
    # 'Default Title' already exists" under DEFAULT - REMOVE_STANDALONE_VARIANT's
    # own documented behavior ("deletes the existing standalone variant")
    # is unambiguous across API versions, DEFAULT's evidently is not.
    _PRODUCT_VARIANTS_BULK_CREATE = """
    mutation productVariantsBulkCreate($productId: ID!, $variants: [ProductVariantsBulkInput!]!, $strategy: ProductVariantsBulkCreateStrategy) {
      productVariantsBulkCreate(productId: $productId, variants: $variants, strategy: $strategy) {
        userErrors { field message }
        productVariants { id }
      }
    }
    """

    # Verified 2026-10-11 - see docs/SOURCES.md "Orders list query".
    _LIST_RECENT_ORDERS = """
    query ListRecentOrders($first: Int = 10) {
      orders(first: $first, sortKey: CREATED_AT, reverse: true) {
        edges {
          node {
            id
            displayFinancialStatus
            totalPriceSet {
              shopMoney { amount currencyCode }
            }
            lineItems(first: 10) {
              edges {
                node {
                  id
                  name
                  quantity
                  originalUnitPriceSet { shopMoney { amount currencyCode } }
                  product {
                    metafield(namespace: "nexus_commerce", key: "cj_product_id") { value }
                  }
                }
              }
            }
            shippingAddress {
              name
              address1
              city
              countryCodeV2
              province
              zip
              phone
            }
          }
        }
      }
    }
    """

    # Verified 2026-10-11 - see docs/SOURCES.md "Variant price update".
    _GET_PRODUCT_FIRST_VARIANT = """
    query GetProductFirstVariant($id: ID!) {
      product(id: $id) {
        id
        variants(first: 1) {
          nodes { id }
        }
      }
    }
    """

    _UPDATE_VARIANT_PRICE = """
    mutation UpdateVariantPrice($productId: ID!, $variantId: ID!, $newPrice: Money!) {
      productVariantsBulkUpdate(
        productId: $productId
        variants: [{ id: $variantId, price: $newPrice }]
      ) {
        product { id }
        productVariants { id price }
        userErrors { field message }
      }
    }
    """

    # Verified 2026-10-11 - see docs/SOURCES.md "Fulfillment tracking update".
    _GET_ORDER_FULFILLMENT_IDS = """
    query OrderFulfillmentIds($id: ID!) {
      order(id: $id) {
        id
        fulfillments(first: 10) { id }
      }
    }
    """

    _UPDATE_FULFILLMENT_TRACKING = """
    mutation FulfillmentTrackingInfoUpdate(
      $fulfillmentId: ID!
      $trackingInfoInput: FulfillmentTrackingInput!
      $notifyCustomer: Boolean
    ) {
      fulfillmentTrackingInfoUpdate(
        fulfillmentId: $fulfillmentId
        trackingInfoInput: $trackingInfoInput
        notifyCustomer: $notifyCustomer
      ) {
        fulfillment { id }
        userErrors { field message }
      }
    }
    """

    # Verified 2026-10-12 - see docs/SOURCES.md "Shopify > Client
    # credentials access token". "apps that act only on stores in your own
    # organization" (this project's exact case) request a token directly
    # with no merchant-install step.
    #
    #   POST https://{shop}.myshopify.com/admin/oauth/access_token
    #   Content-Type: application/x-www-form-urlencoded
    #   grant_type=client_credentials&client_id=...&client_secret=...
    #
    # Response: {"access_token": "...", "scope": "...", "expires_in": 86399}
    # - roughly 24h, so this project re-authenticates per process rather
    # than persisting a token, same as it already does for CJ.

    def __init__(self, shop_url: str, client_id: str, client_secret: str, api_version: str):
        import shopify

        self._shopify = shopify
        self._shop_url = shop_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._api_version = api_version
        self._access_token: str | None = None

    def _get_access_token(self) -> str:
        if self._access_token is None:
            import httpx

            response = httpx.post(
                f"https://{self._shop_url}/admin/oauth/access_token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                timeout=30,
            )
            payload = response.json()
            if "access_token" not in payload:
                raise RuntimeError(f"Shopify authentication failed: {payload}")
            self._access_token = payload["access_token"]
        return self._access_token

    def _execute(self, query: str, variables: dict) -> dict:
        import json

        session = self._shopify.Session(self._shop_url, self._api_version, self._get_access_token())
        self._shopify.ShopifyResource.activate_session(session)

        raw = self._shopify.GraphQL().execute(query=query, variables=variables)
        # shopify.GraphQL().execute()'s return type (str vs already-parsed
        # dict) was not confirmed this session - handle both rather than
        # assume one, per docs/SOURCES.md "Shopify (ShopifyAPI Python package)".
        payload = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        if payload.get("errors"):
            raise RuntimeError(f"Shopify GraphQL request error: {payload['errors']}")
        return payload["data"]

    def get_recent_orders(self) -> list[ShopifyOrder]:
        orders = self._execute(self._LIST_RECENT_ORDERS, {"first": 10})["orders"]
        result = []
        for edge in orders["edges"]:
            node = edge["node"]
            line_items = [
                {
                    "id": li["node"]["id"],
                    "name": li["node"]["name"],
                    "quantity": li["node"]["quantity"],
                    "price": li["node"]["originalUnitPriceSet"]["shopMoney"]["amount"],
                    # Found live 2026-10-14: this was never fetched at all,
                    # so order_fulfillment.py's CJ_ORDER proposals carried
                    # no way to know which CJ product to re-order for a
                    # real paid order - see src/workflows/executor.py. Same
                    # metafield create_product() already writes (verified,
                    # see "Product get with metafields"), read via the line
                    # item's own product reference - a deleted/custom line
                    # item has no "product" at all, so this defaults to ""
                    # rather than crashing.
                    "cj_product_id": (
                        (li["node"].get("product") or {}).get("metafield") or {}
                    ).get("value", ""),
                }
                for li in node["lineItems"]["edges"]
            ]
            shipping_address = node.get("shippingAddress") or {}
            result.append(
                ShopifyOrder(
                    order_id=node["id"],
                    # "PAID" -> "paid" - see docs/SOURCES.md "Orders list query".
                    financial_status=node["displayFinancialStatus"].lower(),
                    total_price=float(node["totalPriceSet"]["shopMoney"]["amount"]),
                    line_items=line_items,
                    shipping_address={
                        "name": shipping_address.get("name"),
                        "address1": shipping_address.get("address1"),
                        "city": shipping_address.get("city"),
                        "country_code": shipping_address.get("countryCodeV2"),
                        # Found live 2026-10-14: CJ's create_order() already
                        # reads "province"/"zip"/"phone" from this dict (see
                        # cj_client.py), but this query never asked Shopify
                        # for them - every real CJ order so far would have
                        # sent empty strings for all three. Verified real
                        # field names from shopify.dev's own MailingAddress
                        # schema (province/zip/phone, not a guess).
                        "province": shipping_address.get("province"),
                        "zip": shipping_address.get("zip"),
                        "phone": shipping_address.get("phone"),
                    } if shipping_address else {},
                )
            )
        return result

    def create_product(
        self, *, title: str, description: str, price: float, images: list[str], cj_product_id: str = ""
    ) -> str:
        media = [
            {"originalSource": url, "mediaContentType": "IMAGE", "alt": title} for url in images
        ]
        # cj_product_id is stored as a metafield (see _LIST_PRODUCTS /
        # get_products() below) - it's this project's own data, not a
        # native Shopify product field, so it has nowhere else to live.
        metafields = (
            [
                {
                    "namespace": self._CJ_PRODUCT_ID_NAMESPACE,
                    "key": self._CJ_PRODUCT_ID_KEY,
                    "type": "single_line_text_field",
                    "value": cj_product_id,
                }
            ]
            if cj_product_id
            else []
        )
        created = self._execute(
            self._PRODUCT_CREATE,
            {"title": title, "descriptionHtml": description, "media": media, "metafields": metafields},
        )["productCreate"]
        if created["userErrors"]:
            raise RuntimeError(f"productCreate failed: {created['userErrors']}")
        product_id = created["product"]["id"]

        priced = self._execute(
            self._PRODUCT_VARIANTS_BULK_CREATE,
            {
                "productId": product_id,
                # ProductVariantsBulkInput.price is the Money SCALAR (a bare
                # decimal string, e.g. "9.99"), not a {amount, currencyCode}
                # object - found live on 2026-10-13 when Shopify rejected the
                # object shape as "invalid money". Verified against
                # shopify.dev's own Money scalar page, see docs/SOURCES.md.
                #
                # inventoryPolicy: CONTINUE - found live 2026-10-14: every
                # product this project had ever published was real (status
                # ACTIVE) but unbuyable - Shopify's own default,
                # inventoryPolicy=DENY, blocks checkout once inventory hits
                # zero, and this store never holds real stock at all (CJ
                # fulfils on demand per order). The owner saw this as "the
                # store is empty" - the 6 real products already live were
                # fixed directly against the real API (see docs/SOURCES.md),
                # this stops every future one from shipping broken the
                # same way.
                "variants": [{"price": str(price), "inventoryPolicy": "CONTINUE"}],
                "strategy": "REMOVE_STANDALONE_VARIANT",
            },
        )["productVariantsBulkCreate"]
        if priced["userErrors"]:
            raise RuntimeError(f"productVariantsBulkCreate failed: {priced['userErrors']}")

        return product_id

    def get_products(self) -> list[ShopifyProduct]:
        products = self._execute(self._LIST_PRODUCTS, {"first": 50})["products"]
        result = []
        for edge in products["edges"]:
            node = edge["node"]
            metafield = node.get("metafield")
            result.append(
                ShopifyProduct(
                    product_id=node["id"],
                    title=node["title"],
                    price=float(node["priceRangeV2"]["minVariantPrice"]["amount"]),
                    inventory=node["totalInventory"],
                    cj_product_id=metafield["value"] if metafield else "",
                )
            )
        return result

    def update_price(self, product_id: str, new_price: float) -> None:
        product = self._execute(self._GET_PRODUCT_FIRST_VARIANT, {"id": product_id})["product"]
        if product is None or not product["variants"]["nodes"]:
            raise RuntimeError(f"no variant found for product {product_id}")
        variant_id = product["variants"]["nodes"][0]["id"]

        # $newPrice as a string, not a bare number - see docs/SOURCES.md
        # "Variant price update" for why this detail isn't fully confirmed.
        result = self._execute(
            self._UPDATE_VARIANT_PRICE,
            {"productId": product_id, "variantId": variant_id, "newPrice": str(new_price)},
        )["productVariantsBulkUpdate"]
        if result["userErrors"]:
            raise RuntimeError(f"productVariantsBulkUpdate failed: {result['userErrors']}")

    def update_tracking(self, order_id: str, tracking_number: str, carrier: str) -> None:
        order = self._execute(self._GET_ORDER_FULFILLMENT_IDS, {"id": order_id})["order"]
        if order is None or not order["fulfillments"]:
            raise RuntimeError(f"no fulfillment found for order {order_id}")
        fulfillment_id = order["fulfillments"][0]["id"]

        # notifyCustomer=True is this project's own choice, not Shopify's -
        # see docs/SOURCES.md "Fulfillment tracking update".
        result = self._execute(
            self._UPDATE_FULFILLMENT_TRACKING,
            {
                "fulfillmentId": fulfillment_id,
                "trackingInfoInput": {"company": carrier, "number": tracking_number},
                "notifyCustomer": True,
            },
        )["fulfillmentTrackingInfoUpdate"]
        if result["userErrors"]:
            raise RuntimeError(f"fulfillmentTrackingInfoUpdate failed: {result['userErrors']}")


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
