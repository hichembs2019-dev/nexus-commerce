# Sources

Every external API detail actually used in this codebase is sourced here. Where
a detail could not be verified, it lives in `UNVERIFIED.md` instead and is not
used.

## Network access note (read this first)

This session's outbound network policy blocks three of the four documentation
domains this project needed:

- `shopify.dev` → proxy returned `403` (organization policy denial)
- `core.telegram.org` → proxy returned `403`
- `developers.cjdropshipping.com` → proxy returned `403`

Confirmed via `curl -sS -o /dev/null -w "%{http_code}" <url>` through the
session's own egress proxy, each returning `CONNECT tunnel failed, response
403`, and independently via `curl -sS "$HTTPS_PROXY/__agentproxy/status"`,
which reports no transient relay failures - this is a policy decision, not a
flaky network. Per this proxy's own operating instructions
(`/root/.ccr/README.md`): "Do not retry or route around it — report the
blocked host." This is reported here rather than worked around by guessing.

Where possible, equivalent information was obtained from **different**,
independently-reachable, still-authoritative sources (an official package's
own README/source on GitHub, raw.githubusercontent.com, pypi.org) - not by
circumventing the block, but by using a different legitimate source that
happened to already be reachable. Where no such alternative existed, the
detail is in `UNVERIFIED.md` and the code does not depend on it.

## Anthropic (Claude)

- https://platform.claude.com/docs/en/api/messages (redirect target of
  docs.claude.com/en/api/messages, fetched directly) - confirmed the
  `messages.create` request shape.
- https://pypi.org/project/anthropic/ - confirmed the official Python client
  instantiation and call pattern:
  ```python
  from anthropic import Anthropic
  client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
  message = client.messages.create(
      model="claude-...-...",  # example on the page used "claude-opus-5-5"
      max_tokens=1024,
      messages=[{"role": "user", "content": "Hello, Claude"}],
  )
  ```
  This project defaults to `claude-sonnet-5-5` per the user's own instruction
  (same family/version-string shape confirmed on this page), configurable via
  `.env`.

## Telegram (python-telegram-bot library, not raw HTTP)

`core.telegram.org` (the raw Bot API docs) is blocked (see above). Instead,
this project depends on the `python-telegram-bot` PyPI package and verified
its actual usage directly from the package's own real example file in its
GitHub repository (reachable via `raw.githubusercontent.com`, not blocked):

- https://raw.githubusercontent.com/python-telegram-bot/python-telegram-bot/master/examples/inlinekeyboard.py
  Confirmed real, quoted code:
  - `InlineKeyboardButton("Option 1", callback_data="1")`
  - `InlineKeyboardMarkup(keyboard)`
  - `await update.message.reply_text("Please choose:", reply_markup=reply_markup)`
  - `query = update.callback_query` / `await query.answer()` / `await query.edit_message_text(text=...)`
  - `application.add_handler(CallbackQueryHandler(button))`
- https://pypi.org/project/python-telegram-bot/ - confirmed the package
  exists and is the one this project depends on; its own page did not include
  the README body, so the example file above (not this page) is the actual
  source for the code shapes used.

**Inferred, not independently fetched**: proactively sending a message from
scheduled code (outside a command handler) as `application.bot.send_message(
chat_id=..., text=..., reply_markup=...)`. This was not found verified
verbatim in either source above. It follows directly from (a) the confirmed
`reply_markup=`/`InlineKeyboardMarkup` shape already quoted above, and (b)
`python-telegram-bot`'s `Application.bot` being a `telegram.Bot` instance (the
library's whole purpose is a 1:1 wrapper around the Bot API, stated on its own
PyPI page), but the exact `send_message` signature was not read from source
this session. Flagged in `UNVERIFIED.md` too; the real client's own code
comment repeats this.

## Shopify (ShopifyAPI Python package)

`shopify.dev` (the Admin GraphQL reference) is blocked (see above). Instead,
this project depends on the official `ShopifyAPI` PyPI package and verified
its actual usage from its own README on GitHub:

- https://raw.githubusercontent.com/Shopify/shopify_python_api/main/README.md
  Confirmed real, quoted code:
  ```python
  import shopify
  shopify.Session.setup(api_key=API_KEY, secret=API_SECRET)
  shop_url = "SHOP_NAME.myshopify.com"
  api_version = '2024-07'
  session = shopify.Session(shop_url, api_version, access_token)
  shopify.ShopifyResource.activate_session(session)
  result = shopify.GraphQL().execute(
      query=document, variables={...}, operation_name="GetOneOrder",
  )
  shopify.ShopifyResource.clear_session()
  ```
  **This package is marked "deprecated and no longer maintained" on its own
  PyPI page**, which recommends a package called `shopifyapp` instead. That
  replacement's own usage was not found/verified this session (see
  `UNVERIFIED.md`) - `ShopifyAPI` is used anyway because its usage pattern
  above is the one this project could actually verify, and it is still
  installable and, per Shopify's own long-standing API version-string
  contract (`'2024-07'`-style versions, visible above), still functions
  against the real Admin API today. This tradeoff - a verified-but-deprecated
  dependency over an unverified-but-current one - is a deliberate choice,
  not an oversight; revisit it once `shopify.dev` is reachable or `shopifyapp`
  can be verified.

Because the actual GraphQL **query/mutation bodies** (product create/update,
order financial-status field name, fulfillment/tracking update) were never
confirmed against any reachable source, none are hardcoded in this project.
See `UNVERIFIED.md` - the real Shopify client raises `NotImplementedError`
at exactly those call sites with a comment pointing here, rather than
guessing field names that Shopify is known to rename across API versions
(e.g. `financialStatus` → `displayFinancialStatus` in past version bumps).

## CJ Dropshipping

`developers.cjdropshipping.com` is blocked. No independently-reachable
alternative source was found (no official or verifiably-official Python
package on PyPI, no mirrored docs located). **Nothing about CJ's actual API
shape is used anywhere in this codebase.** The entire CJ client is an
interface plus a mock; see `UNVERIFIED.md`.
