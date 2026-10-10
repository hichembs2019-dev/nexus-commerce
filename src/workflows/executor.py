"""The only place a consensus-and-Telegram-approved proposal's action_type
turns into a real (or, in DRY_RUN, logged-only) call to Shopify/CJ. Spec SS4
#2: "لا شراء حقيقي، ولا نشر حقيقي... كل شيء يُسجَّل فقط" when DRY_RUN=true -
checked first, before any client is touched, so a real client misconfigured
as non-DRY_RUN can never fire by accident mid-method.
"""
from __future__ import annotations

from ..config import Settings
from ..db.models import ActionType
from ..integrations.cj_client import CJClient
from ..integrations.shopify_client import ShopifyClient


class Executor:
    def __init__(self, shopify: ShopifyClient, cj: CJClient, settings: Settings):
        self._shopify = shopify
        self._cj = cj
        self._settings = settings

    def execute(self, proposal) -> dict:
        if self._settings.dry_run:
            return {
                "success": True,
                "dry_run": True,
                "detail": f"DRY_RUN: would execute {proposal.action_type} with payload {proposal.payload}",
            }

        try:
            return self._execute_real(proposal)
        except Exception as exc:  # noqa: BLE001 - a failed execution is a result, not a crash
            return {"success": False, "dry_run": False, "detail": f"execution error: {exc}"}

    def _execute_real(self, proposal) -> dict:
        payload = proposal.payload

        if proposal.action_type == ActionType.CJ_ORDER.value:
            cj_order_id = self._cj.create_order(
                product_id=payload["product_id"],
                quantity=payload["quantity"],
                shipping_address=payload["shipping_address"],
            )
            return {"success": True, "dry_run": False, "detail": f"CJ order created: {cj_order_id}", "cj_order_id": cj_order_id}

        if proposal.action_type == ActionType.PUBLISH_PRODUCT.value:
            product_id = self._shopify.create_product(
                title=payload["title"],
                description=payload["description"],
                price=payload["price"],
                images=payload.get("images", []),
                cj_product_id=payload.get("cj_product_id", ""),
            )
            return {"success": True, "dry_run": False, "detail": f"product published: {product_id}", "product_id": product_id}

        if proposal.action_type == ActionType.UPDATE_PRICE.value:
            self._shopify.update_price(payload["product_id"], payload["new_price"])
            return {"success": True, "dry_run": False, "detail": "price updated"}

        if proposal.action_type == ActionType.UPDATE_TRACKING.value:
            self._shopify.update_tracking(
                payload["order_id"], payload["tracking_number"], payload.get("carrier", "")
            )
            return {"success": True, "dry_run": False, "detail": "tracking updated"}

        return {"success": False, "dry_run": False, "detail": f"unknown action_type: {proposal.action_type}"}
