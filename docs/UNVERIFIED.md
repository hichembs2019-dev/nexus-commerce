# Unverified

Per the project's own verification rule: anything listed here was **not**
confirmed against a reachable, authoritative source this session, and is
**not used** anywhere in the actual implementation. Where a real client would
need one of these, it raises `NotImplementedError` with a comment pointing
back to this file, rather than guessing. See `SOURCES.md` for exactly which
domains were blocked and why.

## CJ Dropshipping - the entire API surface

`developers.cjdropshipping.com` returned a `403` from this session's egress
proxy (organization policy denial, not a transient failure - see
`SOURCES.md`). No independently-reachable official Python package or mirrored
documentation was found either. Specifically unverified, and therefore not
hardcoded anywhere:

- Base API URL (CJ has historically run both a v1 and v2 API under different
  hosts/paths - which one is current was not confirmed)
- Authentication scheme (API key header name, token exchange flow)
- Product search endpoint and its request/response fields
- Pricing and per-destination-country shipping-cost endpoint and fields
- Order-creation endpoint, request body shape, and response shape
- Shipment-tracking endpoint and response shape

`src/integrations/cj_client.py` defines `CJClient` as an abstract interface
(method names are this project's own domain vocabulary - `search_products`,
`get_shipping_cost`, `create_order`, `track_shipment` - not CJ's own API
vocabulary, which was never seen) and `RealCJClient`, whose every method
raises `NotImplementedError("CJ Dropshipping API not verified - see
docs/UNVERIFIED.md")`. `MockCJClient` is fully implemented and is what every
test and every DRY_RUN run actually exercises.

## Shopify - the GraphQL query/mutation bodies specifically

The `ShopifyAPI` package's own authentication/session/`GraphQL().execute()`
usage **was** verified (see `SOURCES.md`) and is used for real. `productCreate`
+ `productVariantsBulkCreate` (the two mutations behind `create_product()`)
are now verified too and implemented for real - see `SOURCES.md`
"productCreate with images" / "productVariantsBulkCreate (price)". What
remains **not** verified is the GraphQL document text for every other
operation:

- `productUpdate` (or the newer `productSet`) for `update_price()` - exact
  field names and required arguments
- The field name for an order's payment status in the GraphQL schema -
  Shopify has renamed this across API versions before (`financialStatus` in
  older versions, `displayFinancialStatus` more recently) and which is
  correct for whatever API version a real store ends up on was not confirmed
- Fulfillment/tracking-number update mutation name and fields
- Collection (product grouping) mutation names and fields

`src/integrations/shopify_client.py`'s `RealShopifyClient` implements session
setup and `create_product()` exactly as verified; every other method still
raises `NotImplementedError` pointing here. `MockShopifyClient` is fully
implemented and is what every test and DRY_RUN run uses regardless.

## Telegram - proactive `send_message` outside a handler

`python-telegram-bot`'s `reply_text`/`reply_markup`/`InlineKeyboardMarkup`/
`CallbackQueryHandler` shape **was** verified from the library's own example
file (see `SOURCES.md`) and is used for real. Sending a message *proactively*
from the scheduler (not in response to an incoming update) as
`application.bot.send_message(chat_id=..., text=..., reply_markup=...)` was
not independently confirmed from source this session - it is inferred from
the verified `reply_markup=` shape plus `Application.bot` being documented (on
the library's PyPI page) as a `telegram.Bot` instance. This one is judged
low-risk enough to actually use (flagged with a code comment at its one call
site in `src/integrations/telegram_client.py`) rather than stubbed, because:
unlike Shopify's renamed-across-versions GraphQL fields or CJ's entirely
unseen API, `send_message(chat_id, text, reply_markup=...)` is this library's
original, foundational, unchanged-since-inception method - but it is still
named here rather than silently treated as equivalent to the parts that were
directly read from source. If this turns out wrong, it will fail loudly (a
real `TypeError` from a wrong keyword argument), not silently.

## Web search (product/competitor research tool)

The spec names this capability but not a provider, and it isn't one of the
four APIs this project's verification pass covers. `src/tools/web_search.py`
defines the interface and a fully-working mock; `RealWebSearchTool` raises
`NotImplementedError` naming this file. Picking a provider (Anthropic's own
web-search tool-use feature, Bing/Google Custom Search, SerpAPI, ...) is
real, scoped, remaining work.

## Supplier scope (owner's own later instruction widening spec SS1)

The owner explicitly widened "CJ Dropshipping only" to "any legal supplier,
anywhere" (`src/integrations/supplier_client.py`). This widens *sourcing*
only - `new_product_discovery.py` now searches every registered supplier for
the best margin. It does not widen *who gets paid*: `Executor` still resolves
a `CJ_ORDER` proposal's supplier by name and calls that supplier's own
`create_order()` - for any supplier other than "cj" (the only one with a
real-path client today, itself still gated by the CJ section above), that
call raises the same honest `NotImplementedError` rather than guessing a
second, unverified API. `price_inventory_review.py` and `tracking_update.py`
still assume every tracked order's supplier is "cj" - a known, documented
scope limit of this pass, not an oversight.

## What this means in practice

- Every DRY_RUN run and every automated test uses mocks for all four external
  services (Anthropic included, for tests only - DRY_RUN itself does call the
  real Anthropic API for agent reasoning, since that part was fully verified
  and `ANTHROPIC_API_KEY`/`GEMINI_API_KEY` are the project's actual decision-
  making mechanism, not a side effect DRY_RUN needs to suppress).
- `RealCJClient` and parts of `RealShopifyClient` will raise
  `NotImplementedError` if actually called today. This is intentional and
  documented in `README.md`'s "from DRY_RUN to real" section: finishing those
  two files, once `shopify.dev` and CJ's docs are reachable (or someone
  manually provides their current content), is real, scoped, remaining work -
  not a bug to silently work around.
