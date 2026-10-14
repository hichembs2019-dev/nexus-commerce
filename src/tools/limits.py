"""Spec SS4 #4 and SS6: automatic, pre-consensus rejection. These checks run
BEFORE a proposal ever reaches the agents - "أي فعل يتجاوزها يُرفض تلقائياً"
(anything that exceeds them is rejected automatically), not just flagged for
the agents to maybe notice.

Owner's explicit instruction, 2026-10-14 ("ليس هناك حدود للارباح، المهم هناك
ربح... الربح حتى القليل لانه يصبح كثير" - no limit on profit, what matters is
there IS profit, even a small one, because it adds up): there is no longer a
MAX_ORDER_COST/DAILY_SPEND_LIMIT gate (see pipeline.py's `_check_limits` -
every CJ_ORDER proposal is already backed by a Shopify order Shopify itself
already reports as paid, so there is no scenario where this spends the
owner's own money ahead of the customer's), and no fixed minimum-margin
percentage any more - check_margin() below only rejects a proposal whose
real, fee-inclusive profit is zero or negative, never one with a thin but
real positive profit.
"""
from __future__ import annotations

from dataclasses import dataclass

from .profit_calculator import CostBreakdown, profit


@dataclass(frozen=True)
class LimitCheckResult:
    allowed: bool
    reason: str = ""


def check_margin(breakdown: CostBreakdown) -> LimitCheckResult:
    p = profit(breakdown)
    if p <= 0:
        return LimitCheckResult(
            allowed=False,
            reason=f"profit {p} is not positive - sale_price does not even cover its own real costs",
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
