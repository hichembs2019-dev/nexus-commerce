from src.tools.limits import check_margin, check_payment_confirmed
from src.tools.profit_calculator import CostBreakdown

# --- spec-required case: an order before payment is rejected ---


def test_payment_confirmed_allows_paid_orders():
    assert check_payment_confirmed("paid").allowed is True


def test_payment_not_confirmed_rejects_unpaid_orders():
    result = check_payment_confirmed("pending")
    assert result.allowed is False
    assert "paid" in result.reason


def test_payment_not_confirmed_rejects_refunded_orders_too():
    assert check_payment_confirmed("refunded").allowed is False


# --- margin: owner's explicit 2026-10-14 instruction - no fixed floor, only
# "is there a real, fee-inclusive profit at all" (see tools/limits.py).


def test_a_thin_but_real_positive_profit_is_allowed():
    # Old behaviour (a 25% MIN_MARGIN floor) would have rejected this - only
    # 10% margin - which is exactly the case the owner said must now pass.
    breakdown = CostBreakdown(sale_price=100, product_cost=90, shipping_cost=0, shopify_fee=0, payment_processing_fee=0)
    assert check_margin(breakdown).allowed is True


def test_a_large_margin_is_still_allowed():
    breakdown = CostBreakdown(sale_price=100, product_cost=50, shipping_cost=0, shopify_fee=0, payment_processing_fee=0)
    assert check_margin(breakdown).allowed is True


def test_zero_profit_is_rejected():
    breakdown = CostBreakdown(sale_price=100, product_cost=100, shipping_cost=0, shopify_fee=0, payment_processing_fee=0)
    result = check_margin(breakdown)
    assert result.allowed is False
    assert "profit" in result.reason


def test_a_real_loss_is_rejected():
    breakdown = CostBreakdown(sale_price=100, product_cost=110, shipping_cost=5, shopify_fee=0, payment_processing_fee=0)
    result = check_margin(breakdown)
    assert result.allowed is False
