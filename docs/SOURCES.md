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
Dashboard's own "Credenziali"/Credentials page, already visible without any
install step) are the only two Shopify secrets this project now needs.
Usage, confirmed on the same page: header `X-Shopify-Access-Token:
<access_token>` on `https://{shop}.myshopify.com/admin/api/{version}/graphql.json`
- the `ShopifyAPI` package's own `Session`/`activate_session` already send
this header internally, so no code changes were needed there beyond how the
token itself is obtained.

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
