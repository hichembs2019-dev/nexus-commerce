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

### Client credentials access token - verified 2026-10-12

`shopify.Session(shop_url, api_version, access_token)` above needs a real
`access_token` - the README snippet shows the session API, not how to get
one. Earlier in this session the plan was a manually-obtained static Admin
API token (`shpat_...`) from a merchant-install flow, but that flow kept
dead-ending in this Dev Dashboard app (OAuth redirect needs a real reachable
callback URL, which this project doesn't have). The owner instead opened
`shopify.dev`'s own docs directly (blocked from this project's dev session,
reachable from the owner's device) and used its "Ask assistant" tool, which
pointed to the actually-correct flow for this project's case, with its own
source citations:

> This app only works with stores in your own organization (the owner's
> own store - no merchant-install step needed), so it uses the **Client
> credentials grant** directly, not the install/OAuth-redirect flow.

```
POST https://{shop}.myshopify.com/admin/oauth/access_token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}
```

Response:
```json
{"access_token": "f8563253...", "scope": "read_products,write_products,...", "expires_in": 86399}
```

`expires_in` is ~86399 seconds (~24h) - a short-lived token, not a permanent
one. `RealShopifyClient` therefore does this exchange itself (caching the
result per process, like `RealCJClient` already does for its own access
token) rather than expecting a manually-obtained static token in `.env` -
`SHOPIFY_CLIENT_ID` and `SHOPIFY_CLIENT_SECRET` (both from the Dev
Dashboard's own "Credenziali"/Credentials page) are the only two Shopify
secrets this project now needs.
Usage, confirmed on the same page: header `X-Shopify-Access-Token:
<access_token>` on `https://{shop}.myshopify.com/admin/api/{version}/graphql.json`
- the `ShopifyAPI` package's own `Session`/`activate_session` already send
this header internally, so no code changes were needed there beyond how the
token itself is obtained.

**Correction - verified 2026-10-12, live test then re-read of source:** the
"no merchant-install step needed" claim above was wrong. A live call with the
real `SHOPIFY_CLIENT_ID`/`SHOPIFY_CLIENT_SECRET` from `.env` against
`https://zjwmtu-wn.myshopify.com/admin/oauth/access_token` returned
`400 Oauth error app_not_installed`, not a token - the first live, non-mocked
proof this project had of this exchange, and it contradicted the earlier
"Ask assistant" summary. Re-fetched `shopify.dev`'s own tutorial pages
directly (network policy on this dev session was widened to allow it) rather
than trust the earlier paraphrase:

- https://shopify.dev/docs/apps/build/authentication-authorization/client-credentials-grant.md
  lists three requirements, not one: a Dev Dashboard app, access scopes
  released on a version, **and** "Installed app - You've installed your app
  on your store."
- https://shopify.dev/docs/apps/build/dev-dashboard/create-apps-using-dev-dashboard.md
  "Step 3: Install your app" - open the app in the Dev Dashboard, select
  **Install app** (top of the **Installs** card, or the same action in the
  app row's **⋯** menu), which opens Shopify's own OAuth consent screen in a
  new tab (not a callback URL this project has to host), select/create the
  store, select **Install**.

So the client credentials grant genuinely needs no redirect/callback URL
(that part of the original claim was right - that's what makes it different
from the authorization-code grant), but it is **not** install-free: "install"
here is a one-click action inside the Dev Dashboard itself, done once, not a
merchant-facing OAuth redirect this project would have to implement.

### productCreate - verified 2026-10-11

`shopify.dev` is blocked from this session (see note above), but the owner
fetched it themselves from their own device, using shopify.dev's own "Ask
assistant" tool, and pasted the answer here verbatim, source citation
included:

> API: Admin GraphQL > 2026-07 > Mutations > ProductCreate
> https://shopify.dev/docs/api/admin-graphql/2026-07/mutations/productCreate

```graphql
mutation CreateProduct($title: String!, $descriptionHtml: String) {
  productCreate(
    product: { title: $title, descriptionHtml: $descriptionHtml }
  ) {
    product {
      id
      title
    }
    userErrors {
      field
      message
    }
  }
}
```

Confirmed real and current (API version 2026-07).

### productCreate with images - verified 2026-10-11

Same source (shopify.dev's own "Ask assistant", owner's device), follow-up
answer, source citations included:

> API: Admin GraphQL > 2026-07 > Mutations > ProductCreate
> API: Admin GraphQL > 2026-07 > Input Objects > CreateMediaInput

```graphql
mutation ProductCreateWithImages($title: String!, $descriptionHtml: String) {
  productCreate(
    product: { title: $title, descriptionHtml: $descriptionHtml }
    media: [
      {
        originalSource: "https://example.com/product-image-1.jpg"
        mediaContentType: IMAGE
        alt: "Main product image"
      }
    ]
  ) {
    product {
      id
      title
      media(first: 3) {
        nodes {
          id
          mediaContentType
          preview {
            image {
              url
            }
          }
        }
      }
    }
    userErrors {
      field
      message
    }
  }
}
```

Confirmed: `productCreate` does **not** accept price directly - price lives on
variants, set afterward via `productVariantsBulkCreate` (or `productSet`).
`media` is a top-level argument of `productCreate`, not a product field.

### productVariantsBulkCreate (price) - verified 2026-10-11

Same source, final follow-up, source citations included:

> API: Admin GraphQL > 2026-07 > Mutations > ProductVariantsBulkCreate
> https://shopify.dev/docs/api/admin-graphql/2026-07/mutations/productVariantsBulkCreate
> API: Admin GraphQL > 2026-07 > Input Objects > ProductVariantsBulkInput
> https://shopify.dev/docs/api/admin-graphql/2026-07/input-objects/ProductVariantsBulkInput

```graphql
mutation productVariantsBulkCreate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkCreate(productId: $productId, variants: $variants) {
    userErrors {
      field
      message
    }
    product {
      id
      options {
        id
        name
        values
        position
        optionValues {
          id
          name
          hasVariants
        }
      }
    }
    productVariants {
      id
      title
      selectedOptions {
        name
        value
      }
    }
  }
}
```

Confirmed: price is passed as `variants[n].price`, a `Money` value shaped
`{"amount": "19.99", "currencyCode": "USD"}`. The `"USD"` in that example is
Shopify's own illustrative value, not a confirmed fact about any specific
store's actual currency - `RealShopifyClient` takes it as a configurable
`SHOPIFY_CURRENCY_CODE` (default `"USD"`), a simple documented default like
`MARKUP_MULTIPLIER` elsewhere in this project, not a verified fact.

**`create_product()` is now fully implemented** in
`src/integrations/shopify_client.py` using these two mutations in sequence
(`productCreate` → `productVariantsBulkCreate`). Every other
`RealShopifyClient` method is still unverified - see `UNVERIFIED.md`.

### Order payment status field - verified 2026-10-11

Same source (shopify.dev's own "Ask assistant", owner's device). This answer
did not include an explicit source citation block like the three above it -
noted here plainly rather than treated as equally sourced:

```graphql
query GetOrderPaymentStatus($id: ID!) {
  order(id: $id) {
    id
    displayFinancialStatus
  }
}
```

Confirmed: the field is `displayFinancialStatus` (not `financialStatus`) -
matches the rename `UNVERIFIED.md` had already flagged as a risk before this
was checked. A sample response was also provided, confirming the enum value
is uppercase (`"PAID"`), not `"paid"`:

```json
{"data": {"order": {"id": "gid://shopify/Order/1234567890", "displayFinancialStatus": "PAID"}}}
```

### Orders list query - verified 2026-10-11

Same source, with explicit citations this time:

> API: Admin GraphQL > 2026-07 > Queries > orders
> API: Admin GraphQL > 2026-07 > Objects > OrderConnection and Order fields

```graphql
query ListRecentOrders($first: Int = 10) {
  orders(first: $first, sortKey: CREATED_AT, reverse: true) {
    edges {
      node {
        id
        displayFinancialStatus
        totalPriceSet {
          shopMoney {
            amount
            currencyCode
          }
          presentmentMoney {
            amount
            currencyCode
          }
        }
        lineItems(first: 10) {
          edges {
            node {
              id
              name
              quantity
              originalUnitPriceSet {
                shopMoney {
                  amount
                  currencyCode
                }
              }
            }
          }
        }
        shippingAddress {
          name
          address1
          city
          countryCodeV2
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
```

### Variant price update - verified 2026-10-11

Same source, two answers, neither included an explicit "Sources" citation
block (noted plainly, same as the other un-cited answers above):

```graphql
mutation UpdateVariantPrice($productId: ID!, $variantId: ID!, $newPrice: Money!) {
  productVariantsBulkUpdate(
    productId: $productId
    variants: [{ id: $variantId, price: $newPrice }]
  ) {
    product { id title }
    productVariants { id title price }
    userErrors { field message }
  }
}
```

```graphql
query GetProductFirstVariant($id: ID!) {
  product(id: $id) {
    id
    title
    variants(first: 1) {
      nodes { id title }
    }
  }
}
```

Gap found while implementing this, not from Shopify: `update_price()`'s own
interface only takes `product_id`, not `variant_id` - Shopify's mutation
needs both. `RealShopifyClient.update_price()` now looks the variant id up
via the query above before calling the mutation.

One detail is genuinely unresolved, not guessed past: the example variables
for `$newPrice: Money!` showed a bare JSON number (`19.99`), but every other
Money-shaped field verified this session (`totalPriceSet.shopMoney.amount`,
`productVariantsBulkCreate`'s `price.amount`) was a **string**. The code
sends it as a string (`str(new_price)`) for consistency with those, since
GraphQL string scalars are normally not interchangeable with bare numbers
this is the more defensible choice, but it was not independently re-confirmed
the way the other fields were - worth re-checking before relying on it live.

### Fulfillment tracking update - verified 2026-10-11

Same source, three answers:

```graphql
mutation FulfillmentTrackingInfoUpdate(
  $fulfillmentId: ID!
  $trackingInfoInput: FulfillmentTrackingInput!
  $notifyCustomer: Boolean
) {
  fulfillmentTrackingInfoUpdate(
    fulfillmentId: $fulfillmentId
    trackingInfoInput: $trackingInfoInput
    notifyCustomer: $notifyCustomer
  ) {
    fulfillment {
      id
      status
      trackingInfo(first: 10) {
        company
        number
        url
      }
    }
    userErrors { field message }
  }
}
```

`FulfillmentTrackingInput` shape confirmed from example variables:
`{"company": "UPS", "number": "1Z001985YW99744790"}` - fields are `company`
and `number`, matching the output `trackingInfo { company, number, url }`.

Same architectural gap as `update_price()`: `update_tracking()`'s interface
only takes `order_id`, but the mutation needs a `fulfillmentId`:

```graphql
query OrderFulfillmentIds($id: ID!) {
  order(id: $id) {
    id
    fulfillments(first: 10) { id }
  }
}
```

`RealShopifyClient.update_tracking()` now looks up the order's first
fulfillment id before calling the mutation, mirroring `update_price()`'s
variant lookup. `notifyCustomer: true` is this project's own default (not
from Shopify) - a tracking update with no customer notification defeats the
point of adding one.

**Every `RealShopifyClient` method is now implemented and verified.** No
`NotImplementedError` remains in `src/integrations/shopify_client.py`.
Collection (product grouping) mutations were never implemented - spec's
tool list mentions them but no workflow in this project needs them.

`get_recent_orders()` is now implemented against this exact query. Mapping
decisions (ours, not Shopify's - documented, not guessed from their API):
- `financial_status` is lowercased on the way in (`"PAID"` → `"paid"`) so it
  matches the lowercase convention every mock/test in this project already
  uses (`check_payment_confirmed` compares against `"paid"`).
- `total_price` reads `totalPriceSet.shopMoney.amount`.
- `line_items` is a list of `{id, name, quantity, price}` dicts built from
  `lineItems.edges`.
- `shipping_address` is `None`-safe (a digital-only order may have no
  `shippingAddress`) and maps to `{name, address1, city, country_code}`.

## CJ Dropshipping

`developers.cjdropshipping.com` is blocked from this project's own dev
session (see note above), but on 2026-10-11 the owner opened it directly
from their own device and it loaded - CJ's full official docs site, not an
AI assistant like Shopify's but static reference pages, read and relayed
here page by page.

### Authentication - verified 2026-10-11

From CJ's own docs, "1 Authentication > 1.1 Get access token (POST)":

> https://developers.cjdropshipping.com/en/api/introduction.html (CJ Docs home)

```
POST https://developers.cjdropshipping.com/api2.0/v1/authentication/getAccessToken
Content-Type: application/json

{"apiKey": "<the CJ API Key from the dashboard>"}
```

Response:
```json
{
  "code": 200,
  "result": true,
  "message": "Success",
  "data": {
    "openId": 123456789,
    "accessToken": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "accessTokenExpiryDate": "2021-08-18T09:16:33+08:00",
    "refreshToken": "f7edabe65c3b4a198b50ca8f969e36eb",
    "refreshTokenExpiryDate": "2022-02-07T09:16:33+08:00",
    "createDate": "2021-08-11T09:16:33+08:00"
  },
  "requestId": "...",
  "success": true
}
```

Confirmed two-step credential model, not one flat API key:
1. **CJ API Key** (`CJ_API_KEY` in `.env`): a long-lived credential obtained
   manually once from the CJ dashboard (Apps → install "API" app → API →
   Add API → Type: API Key → copy the generated key).
2. **Access token**: obtained by POSTing that API Key to the endpoint above.
   Valid 180 days; CJ caches it server-side for 24h per account, so calling
   this on every app startup is cheap, not wasteful. Used as the
   `CJ-Access-Token` header value on every other authenticated endpoint
   (confirmed consistently across every other CJ docs page read this
   session: `--header 'CJ-Access-Token: xxxxxxxxxxx'`).

Rate limit noted on the same page: 1 call/second (QPS=1) for this endpoint,
same as other CJ endpoints.

### Product search (search_products) - verified 2026-10-12

From CJ's own docs, "3 Product > 1 Products > 1.2 Product List V2 (GET)".
Note: "1.4 Product List (GET)" exists too but is explicitly marked
**deprecated** in favor of V2 ("backed by elasticsearch... plus keyword
search"), so V2 is what this project uses.

```
GET https://developers.cjdropshipping.com/api2.0/v1/product/listV2
CJ-Access-Token: <access token>
```

Parameters (all optional; `keyWord` is the one this project sets):
`keyWord` (search keyword, string), `page`, `size`, `categoryId`,
`lv2categoryList`, `lv3categoryList`, `countryCode`, `startSellPrice`,
`endSellPrice`, and several more filter/sort fields not used here.

Response:
```json
{
  "code": 200,
  "result": true,
  "message": "Success",
  "data": {
    "pageSize": 20,
    "pageNumber": 1,
    "totalRecords": 1000,
    "totalPages": 50,
    "content": [
      {
        "productList": [
          {
            "id": "04A22450-67F0-4617-A132-E7AE7F8...",
            "nameEn": "Personalized Belly-baring ...",
            "sku": "CJNSSYWY01847",
            "spu": "CJNSSYWY01847",
            "bigImage": "https://cc-west-usa.oss-...",
            "sellPrice": "11.85",
            "nowPrice": "9.50"
          }
        ],
        "relatedCategoryList": [{"categoryId": "xxx", "categoryName": "Hoodies"}],
        "keyWord": "hoodie",
        "keyWordOld": "hoodie"
      }
    ]
  },
  "requestId": "..."
}
```

`RealCJClient.search_products()` maps `id` → `CJProduct.product_id`,
`nameEn` → `title`, `sellPrice` (string) → `price` (float).

One detail genuinely not confirmed from the (horizontally-cut-off) `CURL`
block: whether `GET /product/listV2`'s parameters go as a query string or a
JSON body. The code sends them as query parameters - the standard HTTP/REST
convention for a `GET` endpoint - but this project's own earlier CJ pages
(Storage) showed `GET` endpoints still using `--data-raw` JSON bodies in
their `curl` examples, so this is a reasonable default, not a confirmed
fact. Worth re-checking against a real response before relying on it.

### Product details (get_product) - verified 2026-10-12

From CJ's own docs, "3 Product > 1 Products > 1.5 Product Details (GET)".

```
GET https://developers.cjdropshipping.com/api2.0/v1/product/query
CJ-Access-Token: <access token>
```

Parameters: exactly one of `pid` (product id), `productSku`, or
`variantSku` is required; `features` and `countryCode` are optional.
This project always queries by `pid`.

Response (`data`, trimmed to the fields this project reads):
```json
{
  "code": 200,
  "result": true,
  "data": {
    "pid": "000B9312-456A-4D31-94BD-B083E2A198E8",
    "productNameEn": "Small trailer model",
    "sellPrice": 58.09
  }
}
```

Note the field is `productNameEn` here, **not** `nameEn` as in the
`listV2` search response - two different endpoints, two different field
names for the same concept, confirmed from the docs rather than assumed to
match.

`RealCJClient.get_product()` maps `pid` → `CJProduct.product_id`,
`productNameEn` → `title`, `sellPrice` → `price` (float).

### Shipping cost (get_shipping_cost) - verified 2026-10-12

From CJ's own docs, "6 Logistic > 1 Logistics > 1.1 Freight Calculation
(POST)". CJ's own page notes this is "a simple mode of logistics trial
calculation" and points to "1.2 Freight Calculation Tip" for more accuracy
- 1.2 was investigated too, but its required fields (`weight`, `volume`,
`wrapWeight`) have no verified source in this project (no confirmed `volume`
field anywhere in `get_product()`'s response), so 1.1 is used instead: it
needs only a variant id and quantity, which CJ resolves internally.

```
POST https://developers.cjdropshipping.com/api2.0/v1/logistic/freightCalculate
CJ-Access-Token: <access token>
Content-Type: application/json

{
  "startCountryCode": "CN",
  "endCountryCode": "US",
  "products": [{"quantity": 2, "vid": "439FC05B-1311-4349-87FA-1E..."}]
}
```

Response:
```json
{
  "code": 200,
  "result": true,
  "message": "Success",
  "data": [
    {"logisticAging": "2-5", "logisticPrice": 4.71, "logisticPriceCn": 30.54, "logisticName": "USPS+"}
  ],
  "requestId": "...",
  "success": true
}
```

`data` is a list of shipping options; `RealCJClient.get_shipping_cost()`
uses the first option's `logisticPrice` (USD) as a simple, documented
choice - CJ doesn't mark one option as "recommended" in this response shape,
same kind of simple-default decision as `MARKUP_MULTIPLIER` elsewhere in
this project.

`startCountryCode` is hardcoded `"CN"` - every CJ example seen this session
ships from China, and this project has no configured alternate origin.

**Explicitly flagged, not guessed past**: `products[].vid` is a *variant*
id, not the *product* id `CJProduct.product_id` carries. For a product with
no real variants these may coincide, but this was never confirmed - the
code passes `product_id` as `vid` directly, documented here as an assumption
worth re-checking against a real product once a real CJ account is paying
for calls, not treated as equivalent to the parts of this integration that
were independently confirmed field-by-field.

### Create order (create_order) - verified 2026-10-12

From CJ's own docs, "5 Shopping > 1 Order > 1.2 Create Order V3 (POST)" -
chosen over "1.1 Create Order V2" since V3 is the page actively documented
with current guidance (V2 was not opened/compared directly, but V3's own
page actively warns its *own* `cjPayUrl` field is deprecated, which is the
kind of explicit currency signal this project looks for before trusting an
endpoint - see `UNVERIFIED.md` for what this does and doesn't establish
about V2).

```
POST https://developers.cjdropshipping.com/api2.0/v1/shopping/order/createOrderV3
CJ-Access-Token: <access token>
Content-Type: application/json
```

Confirmed-required fields (`Y` in CJ's own table): `orderNumber` ("a unique
identifier for the order from CJ partner" - i.e. from *this* integration,
not from CJ), `shippingCountryCode`, `shippingCountry`, `shippingProvince`,
`shippingCity`, `shippingCustomerName`, `shippingAddress`, and `products`
(array of `{vid, quantity}`, `storeLineItemId` also shown in the example).
Optional: `shippingZip`, `shippingPhone`, and several more not used here.

Response (`data`, trimmed):
```json
{
  "code": 200, "result": true, "message": "Success",
  "data": {
    "orderId": "123434",
    "orderNumber": "",
    "orderStatus": "",
    "interceptOrderReasons": [{"code": 1001, "message": ""}]
  },
  "requestId": "9eddf3f5-bd3d-4fae-a4f2-028cb90db97"
}
```

`data.orderId` is what `create_order()` returns as CJ's order id.
`interceptOrderReasons` (non-empty when CJ blocks the order, e.g. for
stock/compliance reasons even on a `result: true` response) is checked and
raised on.

**Three gaps found while implementing this, flagged rather than guessed
past, same discipline as every other residual gap in this project:**

1. `products[].vid` is a *variant* id - same unconfirmed
   `product_id == vid` assumption already flagged for `get_shipping_cost()`.
2. `shippingProvince` is required, but this project's `ShopifyOrder.shipping_address`
   (see "Orders list query" above) never captures a province/state field at
   all - `get_recent_orders()`'s verified query doesn't request one. A real
   order to a province-requiring destination will fail this call with a
   clear CJ error naming the missing field, not silently send wrong data.
3. `orderNumber` is required but `CJClient.create_order()`'s own signature
   (`product_id, quantity, shipping_address`) has no order-reference
   parameter to source it from. The code reads an optional
   `shipping_address["order_number"]` if the caller supplies one, else
   generates a random id locally - not traceable back to the originating
   Shopify order. A follow-up pass should thread the real Shopify order id
   through instead; noted here as scoped, known remaining work, not an
   oversight.

Only fields confirmed `Y` (required) are sent; fields whose meaning wasn't
independently confirmed (`orderFlow`, `storageId`, `shopLogisticsType`,
`payType`) are deliberately left out rather than copied from the example
value without understanding them. `fromCountryCode: "CN"` and
`platform: "shopify"` are included - the former matching this project's
same documented CN-origin default as `get_shipping_cost()`, the latter
directly matching this project's actual platform, both low-risk inclusions
rather than guesses.

### Track shipment (track_shipment) - verified 2026-10-12

This closes the gap `UNVERIFIED.md` had flagged: `logistic/trackInfo`
(verified earlier, see "6 Logistic") needs a shipping *tracking number*,
not a CJ *order id*. From CJ's own docs, "5 Shopping > 1 Order > 1.7 Query
Order (GET)" supplies exactly that link.

```
GET https://developers.cjdropshipping.com/api2.0/v1/shopping/order/getOrderDetail?orderId=210711000018043276
CJ-Access-Token: <access token>
```

Parameter: `orderId` (string, required).

Response (`data`, trimmed to the fields this project reads):
```json
{
  "code": 200, "result": true, "message": "Success",
  "data": {
    "orderId": "210823100016290555",
    "orderStatus": "CREATED",
    "logisticName": "CJPacket Ordinary",
    "trackNumber": null,
    "trackingProvider": "Yun_Standard"
  }
}
```

CJ's own "Order Status" table (same page) documents the lifecycle:
`CREATED` → `IN_CART` → `UNPAID` → `PENDING`/`PROCESSING` (sub-statuses of
`UNSHIPPED`) → `SHIPPED` ("in transit, get tracking number") → `DELIVERED`
/ `CANCELLED`. `trackNumber` is `null` until the order reaches `SHIPPED` -
confirmed from CJ's own docs, not assumed.

`RealCJClient.track_shipment()` now does this in two real steps:
1. `GET /shopping/order/getOrderDetail?orderId=<cj_order_id>` to read
   `trackNumber` (and `orderStatus`/`logisticName` as a fallback when no
   tracking number exists yet - an order not yet shipped is a normal state,
   not an error).
2. If a `trackNumber` exists, `GET /logistic/trackInfo?trackNumber=...`
   (already verified) for the live carrier status.

Every method on `CJClient` is now verified and implemented. No
`NotImplementedError` remains in `src/integrations/cj_client.py`.

### Live end-to-end proof - 2026-10-12

Both `RealCJClient` and `RealShopifyClient` were run live, for real, from
this project's own code (not hand-written curl) against the owner's real
accounts, after the dev session's network policy was widened to reach
`developers.cjdropshipping.com` and `*.myshopify.com`:

- `RealCJClient("$CJ_API_KEY", ...).search_products("phone case")` returned
  10 real live CJ products with real prices and real CJ product ids.
- `RealShopifyClient(...).get_recent_orders()` authenticated for real
  (`client_credentials` grant, real `shpat_...` access token, scope
  `write_products,write_orders,write_fulfillments`) and queried the real
  store's live Admin API - 0 orders, correct for a brand-new dev store with
  none yet, not an error.

**Shopify install fix, found live, not in any doc paraphrase:** the Dev
Dashboard app's released version had `use_legacy_install_flow: true`
(visible on the version's detail page), which routes installs through the
old authorization-code flow and needs a real callback server to complete -
exactly the dead end this project avoided weeks ago by switching to the
client credentials grant in the first place. A released version can't be
edited, so a new version (`nexus-commerce-2`) was created with that
checkbox cleared and `application_url`/`redirect_urls` set to Shopify's own
documented placeholder (`https://shopify.dev/apps/default-app-home`, not
`example.com`, which is explicitly reserved for documentation examples and
says so on the page). Only after releasing that version and re-running
**Install app** on the correct store did `/admin/oauth/access_token` stop
returning `app_not_installed` and start returning a real token.

**Real bug found and fixed by this same live run - not a guess:** CJ's
`sellPrice` field is a single number for a single-variant product but a
`"low -- high"` range STRING (e.g. `"2.13 -- 7.21"`) for a multi-variant
one - `search_products()` crashed on this live with a real product. Fixed
with `_parse_cj_price()` in `src/integrations/cj_client.py`, which takes the
HIGH end of a range (cost estimates must never be optimistic, given the
owner's own standing instruction that a purchase must never become a loss).
Regression tests: `test_search_products_parses_a_price_range_sellprice_using_the_high_end`
and `test_get_product_parses_a_price_range_sellprice_using_the_high_end` in
`tests/test_real_cj_client.py` - both mutation-tested (fail with the fix
reverted to bare `float()`, pass with it restored).

### get_products() - found missing live, verified 2026-10-13

The live hourly cycle (real run, DRY_RUN=false) hit
`NotImplementedError` from `RealShopifyClient.get_products()` - this
method was never implemented despite `docs/UNVERIFIED.md` and `README.md`
both having said "zero `NotImplementedError` remains" after the earlier
verification pass. That claim was wrong; this live failure is the actual
proof, not the earlier paraphrase. Fetched shopify.dev's own pages
directly (network now open) rather than guess the shape:
- https://shopify.dev/docs/api/admin-graphql/latest/objects/Product.md -
  `totalInventory` ("The quantity of inventory that's in stock") and
  `priceRangeV2.minVariantPrice.amount` give inventory/price without a
  second per-variant query, since every product this project creates has
  exactly one variant (`create_product()` always calls
  `productVariantsBulkCreate` with a single variant). `product.metafield(namespace:, key:)`
  returns `Metafield` (nullable - no `!` in its type, unlike `metafields`
  which is `MetafieldConnection!`), confirming a product with no such
  metafield returns `null`, not an error - matches the code's
  `metafield["value"] if metafield else ""`.
- https://shopify.dev/docs/api/admin-graphql/latest/mutations/productCreate.md -
  the "Create a product and associate metafields" example shows
  `productCreate(product: {..., metafields: [{namespace, key, type, value}]})`,
  confirming metafields can be set in the same mutation that creates the
  product, no second call needed.

**Real gap this closes, not previously flagged anywhere:** `cj_product_id`
is this project's own data (which CJ product a Shopify listing came from) -
Shopify has no native field for it. `ShopifyProduct.cj_product_id` existed
in the dataclass and `MockShopifyClient` faked it in memory, but
`RealShopifyClient.create_product()` never actually persisted it anywhere
real, so even a correctly-implemented `get_products()` could never have
recovered it. Fixed by storing it as a metafield
(namespace `nexus_commerce`, key `cj_product_id`) at creation time and
reading it back the same way - see `_CJ_PRODUCT_ID_NAMESPACE`/`_CJ_PRODUCT_ID_KEY`
and `_LIST_PRODUCTS` in `src/integrations/shopify_client.py`. Without this,
`price_inventory_review.py`'s `if not product.cj_product_id: continue`
would have silently skipped every real product, forever - the workflow
would never visibly fail, it would just never do anything.

### productVariantsBulkCreate strategy - found live, verified 2026-10-13

Live-testing `create_product()` end to end (not just unit tests) on the
owner's real store surfaced two more real bugs the unit tests, written
against a hand-constructed fake response, could not have caught:

1. **"invalid money" on the variant price.** The code sent
   `{"price": {"amount": "9.99", "currencyCode": "USD"}}`. Checked
   https://shopify.dev/docs/api/admin-graphql/latest/scalars/Money.md
   directly: `Money` is "a monetary value string without a currency symbol
   or code" - a bare scalar like `"9.99"`, not an object - and
   https://shopify.dev/docs/api/admin-graphql/latest/input-objects/ProductVariantsBulkInput.md
   confirms `price: Money`. Fixed to `{"price": str(price)}`.
2. **"The variant 'Default Title' already exists."** `productCreate` with
   no explicit variants auto-creates one default variant; the follow-up
   `productVariantsBulkCreate` then collided with it. The mutation's own
   `strategy` argument defaults to `DEFAULT`, whose doc text
   ("deletes the standalone default variant when it's the only variant")
   says this shouldn't happen - but it did, live, on API version
   `2024-07`. Rather than trust the doc text over the live result, switched
   to the version-unambiguous `REMOVE_STANDALONE_VARIANT` value (see
   https://shopify.dev/docs/api/admin-graphql/latest/enums/ProductVariantsBulkCreateStrategy.md),
   whose description is the same behavior stated without "default
   strategy" qualifications that could vary by API version.

**Full live proof, 2026-10-13:** created a real product
(`gid://shopify/Product/16145462788430`) on `zjwmtu-wn.myshopify.com` with
a real price and a real `cj_product_id` metafield, read it back via
`get_products()` and got an exact match (price, metafield value, title all
round-tripped correctly), then deleted it via a direct `productDelete`
mutation to leave the real store clean - this was a one-off manual cleanup
script, not project code, since `ShopifyClient`'s interface has no
`delete_product()` (not needed by any workflow).

## Web search tool - verified 2026-10-13

A real live run of `run_daily()` (manual trigger, not waiting for midnight)
hit `NotImplementedError` from `RealWebSearchTool.search()` - this was the
actual root cause silently blocking every real new-product-discovery cycle
from ever reaching the 5 agents, since `new_product_discovery.py` calls
`web_search.search()` for every candidate that clears `MIN_MARGIN` before
proposing it. `docs/UNVERIFIED.md` already named this gap honestly; this
live failure is what it looks like in practice, not a new finding - but it
is the first proof, since this project's DRY_RUN runs and tests all use
`MockWebSearchTool` and had no way to surface it.

Picked Claude's own server-side web search tool as the provider -
`ANTHROPIC_API_KEY` is already configured and verified for the 5 agents'
reasoning, so no new account or credential is needed. Fetched
https://docs.claude.com/en/docs/agents-and-tools/tool-use/web-search-tool
directly:

- Three tool-type versions exist: `web_search_20250305` (basic),
  `web_search_20260209` (adds dynamic filtering, Claude 4.6+ models),
  `web_search_20260318` (adds `response_inclusion`). Used
  `web_search_20260209` - `CLAUDE_MODEL=claude-sonnet-5-5` supports it, and
  this project needs neither dynamic filtering nor response inclusion
  control.
- Tool declaration: `{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}`
  - `max_uses` caps how many searches one call can run; 3 is this
    project's own choice (a product/competitor check is a simple query, not
    multi-entity research), not a documented requirement.
- Response shape, from the doc's own example: a `web_search_tool_result`
  content block with `tool_use_id` and a `content` list of
  `web_search_result` items, each carrying `url`, `title`, `page_age`, and
  `encrypted_content`. **No snippet/excerpt field exists on the result
  item itself** - confirmed by reading the doc's field list, not assumed.
  `cited_text` (up to 150 characters) exists only on citation objects
  attached to the model's own generated text, not on the raw result. Since
  `new_product_discovery.py` only counts `competitor_research` results and
  never reads `.snippet`, `RealWebSearchTool.search()` leaves `snippet=""`
  rather than inventing content for a field nothing reads.
- `content` is a *list* on success; on a server-tool error it is a single
  error object instead (e.g. `{"type": "web_search_tool_result_error", "error_code": "max_uses_exceeded"}`)
  - `isinstance(content, list)` guards this so one failed search doesn't
    crash the whole discovery cycle.

**Live proof, 2026-10-13:** `RealWebSearchTool(api_key, model).search("wireless earbuds price")`
against the real Anthropic API returned 9 real results with real titles and
URLs (JLab, AT&T, soundcore, Skullcandy, SoundGuys, ...). Wired into
`build_app()` to share the same credential as the 5 agents' own reasoning
client, falling back to `MockWebSearchTool` under the same
`anthropic_configured` gate the reasoning clients already use.

## Gemini agent reasoning - verified 2026-10-13

The owner's own request: several free AI providers working together, not
spending more of the Anthropic balance (out of credit - see the live-proof
entry above). Installed `google-genai` 2.30.0 and used
`inspect.signature()` on the real installed SDK rather than guess its
shape (same discipline as `bootstrap_retries` earlier in this project):
`genai.Client(api_key=...)` and `client.models.generate_content(model=,
contents=, config=)` both confirmed directly from the installed package,
not from the quickstart page's prose alone.

**Model name churn, found live, not from the docs page:**
- `gemini-2.5-flash` (what `ListModels` returned for this key) -> live
  `404`: `"This model ... is no longer available to new users. ... use
  models/gemini-3.8-flash"`.
- `gemini-3.8-flash` (what Google's own error told us to use, and what
  https://ai.google.dev/gemini-api/docs/quickstart's own example uses) ->
  live `503 UNAVAILABLE`, `"currently experiencing high demand"` -
  reproduced on three separate occasions minutes apart, including a direct
  re-test after the owner pasted a Gemini-assistant-suggested snippet using
  the same model - still 503 at that moment. A generic chat answer about
  "which model is free" is not the same claim as "this specific key can
  reach this specific model right now"; the live response from Google's
  own servers is what's authoritative here, not training-data-era general
  advice.
- `gemma-4-26b-a4b-it` (an open Gemma model, also listed for this key) ->
  live `200 OK` with a real reply - the one that actually works for this
  account right now. Set as `GEMINI_MODEL`'s default in `src/config.py`.

**Two real bugs found only by testing the agent-shaped call, not a bare
"say OK" call:**
1. `config=types.GenerateContentConfig(system_instruction=...)` -> live
   `500 Internal Server Error` on `gemma-4-26b-a4b-it` specifically (not on
   content without a system prompt). Fixed by folding the system prompt
   into `contents` instead (`f"{system_prompt}\n\n{user_prompt}"`), which
   works on both Gemini and Gemma models - no model-family branching
   needed.
2. Even past that fix, a live `run_daily()` call showed roughly **half** of
   real `generateContent` calls to `gemma-4-26b-a4b-it` returning `500
   Internal Server Error` - transient (the identical request retried
   plain succeeds). `src/agents/consensus.py`'s `run_consensus()` requires
   `all(d.vote == "approve" for d in decisions)` - a literal unanimous
   vote from all 5 agents - so a ~50% per-call failure rate makes a full
   round very unlikely to ever pass without a retry (confirmed live: a run
   that produced 10 real candidate proposals reached **zero**
   `consensus_reached`, all 10 `failed_consensus`). Added a 3-attempt
   retry with a 2-second delay in `RealGeminiReasoningClient.complete()`.
3. A longer live run (10 candidates, 1-minute scheduler interval, heavy
   retry volume) then hit `429 Too Many Requests` near the end - the free
   tier's own rate limit, a genuinely different condition from the 500s
   above (quota exhaustion, not server flakiness) - confirmed by `exc.code
   == 429` on `google.genai.errors.ClientError` (500/503 raise
   `ServerError` instead; both share the `APIError` base, found via
   `inspect.getmro()` on the installed package). Given its own, longer
   retry delay (20s vs. 2s) rather than reusing the transient-error one,
   and any other `ClientError` (400 bad request, 401/403 auth) is
   re-raised immediately rather than retried, since those are real bugs,
   not transient conditions.

**Architectural decision, not a workaround:** `build_app()` does NOT split
the 5 agents between Anthropic and Gemini when both are configured.
Because consensus needs all 5 to agree, mixing in a provider that is
currently broken (Anthropic, out of credit) or rate-limited would mean
that agent auto-rejects every proposal forever (`_review_with_fallback`
degrades any exception to a "reject", never a crash) - consensus could
then never be reached, silently, with no error anywhere. So whichever
provider is configured runs ALL 5 agents, never a mix of a working and a
broken one. See the comment above the reasoning-client wiring in
`src/app.py` for how to re-enable a genuine mix once both providers are
independently confirmed healthy.

## Real agent reasoning caught a real data gap - 2026-10-13

A live, single-candidate run through Gemini (the fixes above) finally
produced real, substantive votes instead of only retry/error noise - and
the agents correctly REJECTED the candidate, for real business reasons,
not a bug:

> A2 (round 1): "مصفوفة الصور (images) فارغة، ولا يمكن نشر منتج بدون صور.
> كما أن سعر البيع (0.28) منخفض جداً وقد يؤدي لخسارة مالية عند احتساب رسوم
> بوابة الدفع الفعلية."
> A5 (round 3): "سعر البيع (0.28) منخفض جداً وغير واقعي تجارياً، كما أن
> تكلفة الشحن المسجلة (0) تجعل حسابات الهامش غير دقيقة ومضللة."

This is the owner's own standing instruction working exactly as intended
("there must never be a loss") - but it also exposed a real, pre-existing
bug: `new_product_discovery.py`'s proposal payload always sent `"images":
[]`, for every candidate, always. The real image URL was available the
whole time - `bigImage` in CJ's `listV2` response was documented back in
the original `search_products()` verification (see "Product search"
above) but never mapped onto `CJProduct`. Added `CJProduct.image_url`,
mapped from `bigImage` in `search_products()`, and
`new_product_discovery.py` now sends `[candidate.image_url]` when CJ
provided one (still `[]`, honestly, when it didn't - no fabricated image
URL). `get_product()`'s response (used for already-listed products, not
new ones) was not touched - it has no documented image field and nothing
in this project reads one from it.

## Every scheduled job had been silently failing since the first tick - found live 2026-10-13

Ran the real persistent service (`python -m src.main`, DRY_RUN=false,
`HOURLY_INTERVAL_MINUTES=1`) for the first time since the Gemini fixes, and
its own log showed every single scheduled hourly job step failing:

```
sqlite3.ProgrammingError: SQLite objects created in a thread can only be
used in that same thread. The object was created in thread id ... and
this is thread id ...
```

`db/database.py`'s `connect()` carried a comment claiming "APScheduler jobs
each get their own [connection]" - that was never true. `build_app()`
creates exactly one `App` (one `conn`) at service startup, and
`main.py`'s `lambda: run_hourly(app)` / `lambda: run_daily(app)` close over
that same `app` for every scheduled firing. `BackgroundScheduler` runs each
firing on its own worker thread, a different thread than the one that
created the connection - and `run_hourly()`'s own per-step
`except Exception: logger.exception(...)` quietly absorbed the error every
time, so nothing ever visibly crashed; the hourly pipeline had simply never
worked, since its very first scheduled tick, on any run of this service.
Fixed with `sqlite3.connect(database_path, check_same_thread=False)` -
safe here because APScheduler's default executor never runs two instances
of the same job concurrently and this app never issues overlapping writes
from different jobs at the same instant, which is the actual condition
`check_same_thread` exists to guard against.
`tests/test_database.py` reproduces the exact real exception from a real
background thread and is mutation-tested (fails with the flag removed,
passes with it restored).

**Separately, cleaned up real leftover test data found in the same
session**: `get_products()` on the real store returned two abandoned test
products (`gid://shopify/Product/16145454235982` and
`.../16145457611086`, both titled "nexus-commerce TEST - metafield
verification", both `price=0.0`) from earlier live-verification runs in
this same work session that were never cleaned up like the first one was -
deleted via a direct `productDelete` call, same as before. This is what
caused the `price_inventory_review` step's own real error in the log
("Product not found: pid:TEST-CJ-PRODUCT-ID-123") - a real CJ 404 for a
fake test id, not a new bug.

## Shipping cost was never actually computed anywhere - found live 2026-10-13

The real agent votes above also kept flagging the same second concern
every round: `cost_breakdown`'s `shipping_cost` was `0`. Checked how
widely this reaches, not just in `new_product_discovery.py`:
`grep -rl get_shipping_cost src/` showed it used *nowhere* in the real
business logic - not in discovery, not in `order_fulfillment.py`, not in
`executor.py`. `get_shipping_cost()` itself was verified and implemented
from the start (see "Shipping cost" above), but never actually called -
every margin this project ever calculated was overstated by the real
shipping cost, silently, system-wide.

Scoped the fix to `new_product_discovery.py`, the one place a sale price
is ever set (order fulfillment only re-orders what was already published
at an already-decided price; there is no second pricing decision to fix
there). A real destination doesn't exist yet at discovery time - no
customer has bought anything - so `get_shipping_cost()` needs a
representative one to quote at all. `SHIPPING_ESTIMATE_COUNTRY = "US"` is
this project's own simple, documented choice (the single largest
e-commerce destination CJ ships to), the same kind of plain default this
project already uses elsewhere (`MARKUP_MULTIPLIER`, CN origin in
`get_shipping_cost()` itself) - not a verified fact about this store's
actual customers.

**On a failed quote, the candidate is skipped, not assumed free.** This
project's own standing rule (the owner's own words: a purchase must never
turn into a loss) means a `$0` fallback on a failed shipping lookup would
be exactly the kind of optimism that could cause one - so a `RuntimeError`
from CJ's freight API (no route, service down, anything) now means "can't
verify this won't be a loss," not "assume it's free." `MockCJClient`'s own
`get_shipping_cost()` already defaulted unset lookups to `0.0` rather than
raising, so every existing test's prices were unaffected; three new tests
cover a real non-zero quote reaching the stored `cost_breakdown`, a quote
high enough to fail `MIN_MARGIN`, and a failed quote skipping the
candidate - all three mutation-tested (fail with the real call reverted
to the old hardcoded `shipping_cost=0`, pass with it restored).

## CJ `pid` ≠ `vid`, and a real 1 QPS throttle - found live 2026-10-13

Once real shipping quotes started firing every minute against real CJ
candidates, two more real failures showed up in the live log, both
reproduced directly (not inferred from docs):

1. `POST /logistic/freightCalculate` with a real search-result `id` passed
   as `vid` returned `{"code":1602000,"result":false,"message":"Variant not
   found, vid: 1356875251300044800"}` - a real, repeatable rejection, not a
   transient error.
2. The same endpoint under the owner's 1-minute cadence also returned a real
   `429` with `{"code":1600200,"result":false,"message":"Too Many Requests,
   QPS limit is 1 time/1second"}`.

For (1): `GET /product/query?pid=1356875251300044800` was called with the
exact same id, live, and its real response carried a `data.variants[]` array
whose entries' own `vid` (e.g. `1356875251321016320`) is a genuinely
different value from the `pid` - confirmed by inspecting the full real
response, not assumed. Re-checked `listV2`'s (search) full, untrimmed field
list separately and confirmed it has **no** `vid` field at all - the only
real source for a usable `vid` is `product/query`.

Fix: `RealCJClient._resolve_default_vid(product_id)` calls `product/query`
and returns `data["variants"][0]["vid"]`; `get_shipping_cost()` and
`create_order()` both resolve this before building their request body,
instead of passing the caller's `product_id` straight through as `vid`.
"First variant" is this project's own simple default - no call site today
picks a specific size/color, so there is nothing more specific to choose
from yet (see `docs/UNVERIFIED.md`).

For (2): `RealCJClient._post_with_retry()` retries a `429` response up to 3
times with a 1.5s delay (matching the confirmed real "1 time/1 second"
limit) before giving up - the owner's own explicit choice when asked
("أضف إعادة محاولة لطلب الشحن"), applied to the exact real call that hit it.

Both fixes are mutation-tested in `tests/test_real_cj_client.py`: reverting
`_resolve_default_vid()` (restoring the old `"vid": product_id`) reproduces
the real "Variant not found" shape in the new vid-resolution tests, and
removing the retry reproduces a crash on the real 429 body in the retry
test; both pass again with the fix restored.

## Consensus threshold lowered to 2/5 - owner's explicit decision, 2026-10-14

With both CJ fixes above live, the service ran continuously for ~4.5 real
hours under the owner's own 1-minute cadence. Real result, counted directly
from `proposals.status` in the live database: **20 real candidates reached
a decision; 0 ever reached `consensus_reached` under strict 5/5 literal
unanimity.** Every one of the 20 ended `failed_consensus` after the full 3
rounds (or was still `pending_review`, i.e. mid-round, when the service was
stopped). The live log over that window showed the real cause: Gemini's
free tier returning real `503 Service Unavailable` and `429 Too Many
Requests` responses under the owner's chosen cadence - not bad candidates,
not a bug in `run_consensus()` itself, which was working exactly as
designed (recording every vote, retrying failures, never crashing, never
silently approving a parse failure).

Shown this real, counted result, the owner made an explicit decision: change
`run_consensus()`'s rule from literal 5/5 unanimity to `MIN_APPROVALS = 2`
("صيغها اثنان على خمسة 2/5"). This is a real, owner-directed change to the
project's own business rule, not a workaround invented unprompted - see
`src/agents/consensus.py`'s module docstring for the full reasoning kept
with the code. `AGENT_SYSTEM_PROMPT` (`src/agents/prompts.py`) was also
corrected to stop telling the 5 agents literal unanimity is required, since
that was no longer true and would have misled their own reasoning about
when a vote is decisive.

`tests/test_consensus.py` was rewritten end to end for this (every scenario
depends on how many approvals clear the threshold) and mutation-tested as a
set: reverting the threshold check to `all(d.vote == "approve" ...)`
reproduces 5 real test failures (the boundary tests, the amendment tests,
and the unparseable-reply test, which all now rely on 2/5 semantics to mean
what they assert); restoring `MIN_APPROVALS` passes all of them again. Full
suite: 129 passed.
