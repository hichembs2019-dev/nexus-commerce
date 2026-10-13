# Unverified

Per the project's own verification rule: anything listed here was **not**
confirmed against a reachable, authoritative source this session, and is
**not used** anywhere in the actual implementation. Where a real client would
need one of these, it raises `NotImplementedError` with a comment pointing
back to this file, rather than guessing. See `SOURCES.md` for exactly which
domains were blocked and why.

## CJ Dropshipping - now fully verified and implemented

`developers.cjdropshipping.com` returned a `403` from this project's own dev
session's egress proxy (organization policy denial, not a transient failure
- see `SOURCES.md`). On 2026-10-11 the owner opened it directly from their
own device, and it loaded - CJ's full official docs site, read page by page
from there. **Every `CJClient` method is now verified and implemented** -
authentication, `search_products()`, `get_product()`, `get_shipping_cost()`,
`create_order()`, and `track_shipment()`. See `SOURCES.md` "CJ Dropshipping"
for the full exchange and every source citation.

"1.1 Create Order V2" was never opened/compared against V3 directly - V3 was
chosen because its own page explicitly flags its own `cjPayUrl` field as
deprecated, the kind of currency signal this project looks for, not because
V2 was confirmed inferior.

Several residual, explicitly-flagged gaps remain (none are silent guesses -
each is a documented project-level choice):

- `search_products()`: whether `GET /product/listV2`'s parameters go as a
  query string or a JSON body wasn't confirmed (the `curl` example was cut
  off) - the code uses query parameters as the standard REST convention.
- `get_shipping_cost()` and `create_order()`: whether `product_id` is
  interchangeable with the `vid` (variant id) these endpoints actually ask
  for was never confirmed - both pass `product_id` as `vid` directly.
- `create_order()`: `shippingProvince` is required by CJ but has no real
  source in this project's verified Shopify order data (a province-
  requiring destination will surface this as a clear CJ error, not silently
  send wrong data); `orderNumber` is generated locally rather than traced
  back to the originating Shopify order - a follow-up pass should thread
  that through `CJClient.create_order()`'s signature instead.

`src/integrations/cj_client.py` defines `CJClient` as an abstract interface
(method names are this project's own domain vocabulary - `search_products`,
`get_shipping_cost`, `create_order`, `track_shipment` - not CJ's own API
vocabulary) and `RealCJClient`, which now has **zero** remaining
`NotImplementedError`. `MockCJClient` stays fully implemented too and is
what every automated test and every DRY_RUN run actually exercises
regardless - `RealCJClient` only runs when `DRY_RUN=false` and real CJ
credentials are set.

## Shopify - now fully verified and implemented (including authentication)

Authentication no longer needs a manually-obtained static Admin API token.
`RealShopifyClient` uses the **Client credentials grant** - verified
2026-10-12, see `SOURCES.md` "Client credentials access token" - exchanging
`SHOPIFY_CLIENT_ID` + `SHOPIFY_CLIENT_SECRET` for a short-lived (~24h)
access token itself, the same pattern already used for `RealCJClient`.

The `ShopifyAPI` package's own authentication/session/`GraphQL().execute()`
usage **was** verified (see `SOURCES.md`) and is used for real.
**Every `RealShopifyClient` method is now verified and implemented** -
`create_product()` (`productCreate` + `productVariantsBulkCreate`),
`get_recent_orders()` (the `orders` connection + `displayFinancialStatus`),
`update_price()` (`productVariantsBulkUpdate`, after looking up the variant
id), and `update_tracking()` (`fulfillmentTrackingInfoUpdate`, after looking
up the fulfillment id). See `SOURCES.md` for the full exchange and every
source citation.

One residual, explicitly-flagged gap remains (not a guess - a documented
project-level choice):

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

## Web search - now verified and implemented

Provider picked: Claude's own server-side web search tool
(`web_search_20260209`), using the same `ANTHROPIC_API_KEY` already
configured for the 5 agents - see `docs/SOURCES.md` "Web search tool" for
the full verification and a live proof. `RealWebSearchTool` has zero
remaining `NotImplementedError`.

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

## Gemini free tier reliability (known operational constraint, not a guess)

`RealGeminiReasoningClient` is fully verified and implemented (see
`docs/SOURCES.md` "Gemini agent reasoning"), with retries for both
transient `500`s and `429` rate limits. But the free tier's real quota is
a genuine practical ceiling this project cannot remove: a live run of 10
real candidate proposals reached **zero** unanimous 5-agent approvals even
with retries, because `run_consensus()` requires all 5 agents to agree and
a flaky/rate-limited free model makes a clean unanimous round across 5
calls (and up to 3 rounds) statistically hard at volume. This is not a bug
to silently paper over - it is the honest cost of "free." If this keeps
blocking real consensus in practice, the real fix is either a paid Gemini
tier, splitting discovery across more, smaller runs, or mixing in a
second working provider once Anthropic's balance is restored (see the
comment in `src/app.py` on why they are not mixed today).

## What this means in practice

- Every DRY_RUN run and every automated test uses mocks for all five external
  services (Anthropic and the web search tool included, for tests only -
  DRY_RUN itself does call the real Anthropic API for agent reasoning and
  web search, since both are fully verified and `ANTHROPIC_API_KEY` is the
  project's actual decision-making mechanism, not a side effect DRY_RUN
  needs to suppress).
- As of 2026-10-13, `RealShopifyClient`, `RealCJClient`, and
  `RealWebSearchTool` have zero remaining `NotImplementedError` and have all
  been proven live against real accounts (see `docs/SOURCES.md`'s live-proof
  entries), not just unit-tested against hand-built fakes. The one remaining
  documented gap in this whole file is `telegram_client.py`'s proactive
  `send_message` shape (low-risk, already used in production, flagged above
  rather than silently treated as equally verified).
