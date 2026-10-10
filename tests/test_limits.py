from src.config import Settings
from src.tools.limits import (
    check_daily_spend,
    check_margin,
    check_order_cost,
    check_order_limits,
    check_payment_confirmed,
)
from src.tools.profit_calculator import CostBreakdown


def _settings(**overrides) -> Settings:
    base = dict(max_order_cost=200.0, daily_spend_limit=500.0, min_margin=0.25)
    base.update(overrides)
    return Settings(**base)


# --- spec-required case: exceeding MAX_ORDER_COST is rejected ---

def test_cost_at_or_under_max_order_cost_is_allowed():
    assert check_order_cost(200.0, _settings(max_order_cost=200.0)).allowed is True


def test_cost_over_max_order_cost_is_rejected():
    result = check_order_cost(200.01, _settings(max_order_cost=200.0))
    assert result.allowed is False
    assert "MAX_ORDER_COST" in result.reason


# --- daily spend limit ---

def test_daily_spend_under_limit_is_allowed():
    result = check_daily_spend(50.0, already_spent_today=100.0, settings=_settings(daily_spend_limit=500.0))
    assert result.allowed is True


def test_daily_spend_pushed_over_limit_is_rejected():
    result = check_daily_spend(50.0, already_spent_today=460.0, settings=_settings(daily_spend_limit=500.0))
    assert result.allowed is False
    assert "DAILY_SPEND_LIMIT" in result.reason


def test_daily_spend_exactly_at_limit_is_allowed():
    result = check_daily_spend(40.0, already_spent_today=460.0, settings=_settings(daily_spend_limit=500.0))
    assert result.allowed is True


# --- spec-required case: an order before payment is rejected ---

def test_payment_confirmed_allows_paid_orders():
    assert check_payment_confirmed("paid").allowed is True


def test_payment_not_confirmed_rejects_unpaid_orders():
    result = check_payment_confirmed("pending")
    assert result.allowed is False
    assert "paid" in result.reason


def test_payment_not_confirmed_rejects_refunded_orders_too():
    assert check_payment_confirmed("refunded").allowed is False


# --- margin ---

def test_margin_at_or_above_min_margin_is_allowed():
    breakdown = CostBreakdown(sale_price=100, product_cost=50, shipping_cost=0, shopify_fee=0, payment_processing_fee=0)
    assert check_margin(breakdown, _settings(min_margin=0.25)).allowed is True


def test_margin_below_min_margin_is_rejected():
    breakdown = CostBreakdown(sale_price=100, product_cost=90, shipping_cost=0, shopify_fee=0, payment_processing_fee=0)
    result = check_margin(breakdown, _settings(min_margin=0.25))
    assert result.allowed is False
    assert "MIN_MARGIN" in result.reason


# --- combined order-limit check (used by submit_proposal for CJ_ORDER) ---

def test_check_order_limits_fails_on_per_order_cost_first():
    result = check_order_limits(250.0, already_spent_today=0.0, settings=_settings(max_order_cost=200.0))
    assert result.allowed is False
    assert "MAX_ORDER_COST" in result.reason


def test_check_order_limits_fails_on_daily_total_when_per_order_cost_is_fine():
    result = check_order_limits(60.0, already_spent_today=460.0, settings=_settings(max_order_cost=200.0, daily_spend_limit=500.0))
    assert result.allowed is False
    assert "DAILY_SPEND_LIMIT" in result.reason


def test_check_order_limits_allows_when_both_checks_pass():
    result = check_order_limits(60.0, already_spent_today=100.0, settings=_settings(max_order_cost=200.0, daily_spend_limit=500.0))
    assert result.allowed is True
