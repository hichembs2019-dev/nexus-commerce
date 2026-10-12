# Unverified

Per the project's own verification rule: anything listed here was **not**
confirmed against a reachable, authoritative source this session, and is
**not used** anywhere in the actual implementation. Where a real client would
need one of these, it raises `NotImplementedError` with a comment pointing
back to this file, rather than guessing. See `SOURCES.md` for exactly which
domains were blocked and why.

## CJ Dropshipping - the data API surface (authentication is now verified)

`developers.cjdropshipping.com` returned a `403` from this project's own dev
session's egress proxy (organization policy denial, not a transient failure
- see `SOURCES.md`). On 2026-10-11 the owner opened it directly from their
own device, and it loaded - CJ's full official docs site. Authentication, product search, product
details, and shipping cost are now verified and implemented for real - see
`SOURCES.md` "CJ Dropshipping > Authentication" / "Product search" /
"Product details" / "Shipping cost". Specifically still unverified, and
therefore not hardcoded anywhere:

- Order-creation endpoint, request body shape, and response shape
- Shipment-tracking-by-CJ-order-id flow (the verified `logistic/trackInfo`
  endpoint takes a shipping tracking number, not a CJ order id - how to get
  from one to the other is still unconfirmed, see `SOURCES.md`)

`search_products()` has one residual, explicitly-flagged gap: whether
`GET /product/listV2`'s parameters go as a query string or a JSON body
wasn't confirmed (the `curl` example was cut off) - the code uses query
parameters as the standard REST convention, documented as the defensible
choice, not a certainty. See `SOURCES.md` "Product search".

`get_shipping_cost()` has one residual, explicitly-flagged gap: whether
`product_id` is interchangeable with the `vid` (variant id) the verified
`freightCalculate` endpoint actually asks for was never confirmed. See
`SOURCES.md` "Shipping cost".

`src/integrations/cj_client.py` defines `CJClient` as an abstract interface
(method names are this project's own domain vocabulary - `search_products`,
`get_shipping_cost`, `create_order`, `track_shipment` - not CJ's own API
vocabulary) and `RealCJClient`, whose `__init__`/`_get_access_token()` are
real (the verified token exchange), but every data method still raises
`NotImplementedError("CJ Dropshipping API not verified - see
docs/UNVERIFIED.md")`. `MockCJClient` is fully implemented and is what every
test and every DRY_RUN run actually exercises.

## Shopify - now fully verified and implemented

The `ShopifyAPI` package's own authentication/session/`GraphQL().execute()`
usage **was** verified (see `SOURCES.md`) and is used for real.
**Every `RealShopifyClient` method is now verified and implemented** -
`create_product()` (`productCreate` + `productVariantsBulkCreate`),
`get_recent_orders()` (the `orders` connection + `displayFinancialStatus`),
`update_price()` (`productVariantsBulkUpdate`, after looking up the variant
id), and `update_tracking()` (`fulfillmentTrackingInfoUpdate`, after looking
up the fulfillment id). See `SOURCES.md` for the full exchange and every
source citation.

Two residual, explicitly-flagged gaps remain (neither is a guess - both are
documented project-level choices):

- `update_price()`: whether Shopify's `Money` scalar wants a JSON string or
  a bare number for `$newPrice` was not independently re-confirmed (the
  example used a bare number; every other Money field verified this session
  was a string, and the code follows that pattern for consistency, not
  certainty). See `SOURCES.md` "Variant price update".
- `update_tracking()`: `notifyCustomer: true` is this project's own default,
  not something Shopify's docs specified - a tracking update with no
  customer notification defeats the point of adding one. See `SOURCES.md`
  "Fulfillment tracking update".

Collection (product grouping) mutations were never implemented at all -
spec's tool list mentions them but no workflow in this project needs them.

`src/integrations/shopify_client.py`'s `RealShopifyClient` now has **zero**
remaining `NotImplementedError`. `MockShopifyClient` stays fully implemented
too and is what every automated test and every DRY_RUN run actually
exercises regardless - `RealShopifyClient` only runs when `DRY_RUN=false`
and real Shopify credentials are set.

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
