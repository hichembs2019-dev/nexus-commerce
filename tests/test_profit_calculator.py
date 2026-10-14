from src.tools.profit_calculator import CostBreakdown, margin, profit, total_cost


def test_total_cost_sums_every_component():
    b = CostBreakdown(sale_price=100, product_cost=20, shipping_cost=5, shopify_fee=3, payment_processing_fee=2)
    assert total_cost(b) == 30


def test_profit_is_sale_price_minus_total_cost():
    b = CostBreakdown(sale_price=100, product_cost=20, shipping_cost=5, shopify_fee=3, payment_processing_fee=2)
    assert profit(b) == 70


def test_margin_is_profit_over_sale_price():
    b = CostBreakdown(sale_price=100, product_cost=20, shipping_cost=5, shopify_fee=3, payment_processing_fee=2)
    assert margin(b) == 0.70


def test_margin_with_zero_sale_price_is_negative_infinity_not_a_crash():
    b = CostBreakdown(sale_price=0, product_cost=20, shipping_cost=0, shopify_fee=0, payment_processing_fee=0)
    assert margin(b) == float("-inf")
