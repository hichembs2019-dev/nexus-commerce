"""Pure functions, no I/O - spec SS6's profit formula and margin check. Kept
free of any database/API dependency so it is trivially unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostBreakdown:
    sale_price: float
    product_cost: float
    shipping_cost: float
    shopify_fee: float
    payment_processing_fee: float


def total_cost(breakdown: CostBreakdown) -> float:
    return (
        breakdown.product_cost
        + breakdown.shipping_cost
        + breakdown.shopify_fee
        + breakdown.payment_processing_fee
    )


def profit(breakdown: CostBreakdown) -> float:
    """sale_price - (product_cost + shipping_cost + shopify/payment fees) -
    exactly spec SS6's formula.
    """
    return breakdown.sale_price - total_cost(breakdown)


def margin(breakdown: CostBreakdown) -> float:
    """profit as a fraction of sale price. Zero or negative sale_price has
    no meaningful margin - treated as the worst possible margin (-inf) so it
    always fails a positive-profit check rather than raising or being
    silently treated as acceptable.
    """
    if breakdown.sale_price <= 0:
        return float("-inf")
    return profit(breakdown) / breakdown.sale_price
