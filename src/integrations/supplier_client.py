"""The owner's own explicit widening of spec SS1's "CJ only" rule: the agents
should search for the best margin across *any* supplier, not just CJ, when
looking for new products. SupplierClient reuses CJClient's exact shape - the
interface was never CJ-specific vocabulary to begin with (search_products,
get_shipping_cost, get_product, create_order, track_shipment), so any number
of suppliers can be registered under it with zero new abstractions.

Searching multiple catalogs for the best price is safe to turn on immediately
- it is read-only. Actually *spending money* against a given supplier is not
widened by this file: Executor still only executes a CJ_ORDER against a
supplier whose client is real and verified (today, only "cj" - see
docs/UNVERIFIED.md). A product discovered from an unconfigured/unverified
supplier is proposed, voted on, and sent to Telegram like anything else, but
its own order execution raises a clear, documented error rather than silently
guessing a second supplier's real API the same way CJ's RealCJClient already
refuses to guess CJ's.
"""
from __future__ import annotations

from .cj_client import CJClient, CJProduct


class SupplierRegistry:
    """Named suppliers, each exposing the same CJClient-shaped interface."""

    def __init__(self, suppliers: dict[str, CJClient]):
        if not suppliers:
            raise ValueError("SupplierRegistry needs at least one supplier")
        self._suppliers = dict(suppliers)

    def search_all(self, query: str) -> list[tuple[str, CJProduct]]:
        """Every matching product from every registered supplier, tagged
        with which supplier it came from - new_product_discovery.py picks
        the best margin across all of them, not just one.
        """
        results: list[tuple[str, CJProduct]] = []
        for name, client in self._suppliers.items():
            for product in client.search_products(query):
                results.append((name, product))
        return results

    def get(self, name: str) -> CJClient:
        return self._suppliers[name]

    def __contains__(self, name: str) -> bool:
        return name in self._suppliers

    @property
    def names(self) -> list[str]:
        return list(self._suppliers.keys())
