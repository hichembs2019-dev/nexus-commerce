"""Spec SS4 #4 and SS6: automatic, pre-consensus rejection. These checks run
BEFORE a proposal ever reaches the 5 agents - "أي فعل يتجاوزها يُرفض
تلقائياً" (anything that exceeds them is rejected automatically), not just
flagged for the agents to maybe notice.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from .profit_calculator import CostBreakdown, margin


@dataclass(frozen=True)
class LimitCheckResult:
    allowed: bool
    reason: str = ""


def check_order_cost(cost: float, settings: Settings) -> LimitCheckResult:
    if cost > settings.max_order_cost:
        return LimitCheckResult(
            allowed=False,
            reason=f"cost {cost} exceeds MAX_ORDER_COST {settings.max_order_cost}",
        )
    return LimitCheckResult(allowed=True)


def check_daily_spend(cost: float, already_spent_today: float, settings: Settings) -> LimitCheckResult:
    projected = already_spent_today + cost
    if projected > settings.daily_spend_limit:
        return LimitCheckResult(
            allowed=False,
            reason=(
                f"today's spend {already_spent_today} + this cost {cost} = {projected} "
                f"exceeds DAILY_SPEND_LIMIT {settings.daily_spend_limit}"
            ),
        )
    return LimitCheckResult(allowed=True)


def check_margin(breakdown: CostBreakdown, settings: Settings) -> LimitCheckResult:
    m = margin(breakdown)
    if m < settings.min_margin:
        return LimitCheckResult(
            allowed=False,
            reason=f"margin {m:.2%} is below MIN_MARGIN {settings.min_margin:.2%}",
        )
    return LimitCheckResult(allowed=True)


def check_payment_confirmed(financial_status: str) -> LimitCheckResult:
    """Spec SS4 #5: a CJ order may only be proposed once Shopify reports the
    matching order's financial_status as 'paid' - never earlier.
    """
    if financial_status != "paid":
        return LimitCheckResult(
            allowed=False,
            reason=f"order financial_status is '{financial_status}', not 'paid'",
        )
    return LimitCheckResult(allowed=True)


def check_order_limits(cost: float, already_spent_today: float, settings: Settings) -> LimitCheckResult:
    """Both cost checks a CJ order proposal needs, in one call - the first
    failure wins, since either alone is a complete reason to auto-reject.
    """
    per_order = check_order_cost(cost, settings)
    if not per_order.allowed:
        return per_order
    return check_daily_spend(cost, already_spent_today, settings)
