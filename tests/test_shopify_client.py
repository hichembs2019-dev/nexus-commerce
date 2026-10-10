from src.integrations.shopify_client import MockShopifyClient, ShopifyOrder


def test_create_product_returns_a_usable_id_and_stores_the_product():
    client = MockShopifyClient()

    product_id = client.create_product(title="Widget", description="d", price=19.99, images=[], cj_product_id="cj-1")

    products = client.get_products()
    assert len(products) == 1
    assert products[0].product_id == product_id
    assert products[0].price == 19.99
    assert products[0].cj_product_id == "cj-1"


def test_update_price_mutates_the_stored_product_and_is_recorded():
    client = MockShopifyClient()
    product_id = client.create_product(title="Widget", description="d", price=10.0, images=[])

    client.update_price(product_id, 15.0)

    assert client.get_products()[0].price == 15.0
    assert client.price_updates == [(product_id, 15.0)]


def test_update_tracking_is_recorded():
    client = MockShopifyClient()

    client.update_tracking("order-1", "TRACK123", "DHL")

    assert client.tracking_updates == [("order-1", "TRACK123", "DHL")]


def test_get_recent_orders_returns_seeded_orders():
    client = MockShopifyClient()
    order = ShopifyOrder(order_id="1001", financial_status="paid", total_price=50.0)
    client.orders.append(order)

    assert client.get_recent_orders() == [order]
