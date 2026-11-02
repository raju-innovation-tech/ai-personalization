# API Integration Guide

This document is for the **existing e-commerce team** integrating with the AI Personalization & Offer Engine. It covers everything available as of **Phase 1**. Recommendation and Offer endpoints will be documented here as they ship in Phase 2 and Phase 4.

Base URL (local dev): `http://localhost:8000/api/v1`
Interactive docs: `http://localhost:8000/docs`

## Response Envelope

Every response follows one of two shapes.

**Success:**
```json
{ "success": true, "data": { ... } }
```

**Error:**
```json
{ "success": false, "error": { "code": "USER_NOT_FOUND", "message": "Customer not found" } }
```

Always check `success` before reading `data`.

## Authentication

Phase 1 authentication is for the **Flutter admin dashboard** (staff logging into the BI tool). Server-to-server event ingestion from your e-commerce backend does not yet require a bearer token in Phase 1 — a dedicated service-account / API-key auth model for event ingestion will be finalized and documented here in a later phase before production use. Do not expose the `/events` endpoint on the public internet without a reverse-proxy-level protection (e.g. mTLS, IP allowlist, or an API gateway) until then.

### POST /auth/login
```json
// Request
{ "email": "admin@example.com", "password": "ChangeMe123!" }

// Response 200
{
  "success": true,
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "bearer"
  }
}
```
Access tokens expire in 30 minutes (configurable). Send as `Authorization: Bearer <access_token>`.

### POST /auth/refresh
```json
// Request
{ "refresh_token": "eyJ..." }

// Response 200 — new token pair (old refresh token is invalidated)
{ "success": true, "data": { "access_token": "eyJ...", "refresh_token": "eyJ...", "token_type": "bearer" } }
```

### POST /auth/logout
Requires `Authorization: Bearer <access_token>`. Invalidates the stored refresh token.

### GET /auth/me
Requires `Authorization: Bearer <access_token>`. Returns the current admin user's profile.

## Sending Events

This is the primary integration point for your team. Every meaningful customer action should be sent here — this is what powers recommendations, segmentation, and offers in later phases.

### POST /events (single event)

```json
{
  "event_type": "PRODUCT_VIEW",
  "external_user_id": "USER_10025",
  "product_id": "PROD_500",
  "session_id": "SESSION_123",
  "platform": "mobile",
  "timestamp": "2026-09-25T10:30:00Z",
  "metadata": { "category": "electronics" },
  "idempotency_key": "optional-your-own-uuid"
}
```

**Field notes:**
- `event_type` — one of the 17 supported types (see below). Required.
- `external_user_id` — your platform's user ID. Required. We never generate our own; yours is the source of truth.
- `product_id` — your platform's product ID. Optional (omit for events like `PRODUCT_SEARCH`).
- `timestamp` — **must include a timezone offset** (e.g. `Z` or `+05:30`). Requests without one are rejected with a 422.
- `idempotency_key` — optional. If you omit it, we derive a stable key from `(event_type, external_user_id, product_id, session_id, timestamp)`, so retrying the exact same event is safe either way. Supplying your own is recommended if you already generate event IDs.

**Response 201:**
```json
{ "success": true, "data": { "idempotency_key": "...", "status": "accepted" } }
```
`status` is `"duplicate"` if this exact event was already ingested — this is not an error, just a no-op confirmation. Safe to retry on network failure.

### Supported event_type values

| Event | When to send it |
|---|---|
| `PRODUCT_VIEW` | Customer opens a product detail page |
| `PRODUCT_SEARCH` | Customer performs a search (put the query in `metadata.query`) |
| `CATEGORY_VIEW` | Customer browses a category listing |
| `WISHLIST_ADD` / `WISHLIST_REMOVE` | Wishlist toggled |
| `ADD_TO_CART` / `REMOVE_FROM_CART` | Cart changes |
| `CHECKOUT_STARTED` | Customer begins checkout |
| `PURCHASE` | Order completed |
| `PURCHASE_CANCELLED` | Order cancelled before fulfillment |
| `RETURN` | Product returned |
| `PRODUCT_REVIEW` | Customer leaves a review |
| `OFFER_VIEW` / `OFFER_CLICK` / `OFFER_REDEEM` | Offer shown/clicked/redeemed (Phase 4+) |
| `RECOMMENDATION_VIEW` / `RECOMMENDATION_CLICK` | Recommendation shown/clicked (Phase 2+) |

### POST /events/batch

Send up to 500 events in one call. The batch is validated as a whole: if any event is malformed the request is rejected with `422` and nothing is stored. Valid batches are ingested atomically; events already seen (same `idempotency_key`, including repeats inside the same batch) are reported as `duplicate` and are not stored twice.

```json
{ "events": [ { ...event1 }, { ...event2 } ] }
```

**Response 201:**
```json
{
  "success": true,
  "data": {
    "accepted": 2,
    "duplicates": 0,
    "rejected": 0,
    "results": [
      { "idempotency_key": "...", "status": "accepted" },
      { "idempotency_key": "...", "status": "accepted" }
    ],
    "errors": []
  }
}
```
`errors` is reserved for future soft failures and is currently always empty; malformed events are rejected up-front with a `422` (see error envelope above, `error.details` lists each bad field).

**Recommendation:** batch events client-side over a short window (e.g. every 2–5 seconds or every 20 events) rather than firing one HTTP request per user action, to reduce request volume.

## Health Checks

### GET /health
Liveness only — process is up. No dependency checks. Use for container orchestration liveness probes.

### GET /ready
Checks database and Redis connectivity. Use for readiness probes / load balancer health checks.
```json
{ "success": true, "data": { "status": "ready", "checks": { "database": "ok", "redis": "ok" } } }
```

## Products (catalog sync + admin listing)

Reading needs any logged-in user (`Authorization: Bearer <token>`). **Writing needs role `ADMIN` or `SUPER_ADMIN`** -
your e-commerce backend should log in once with a service account and push catalog changes.

### POST /products  and  POST /products/bulk (up to 500)
Upsert by `product_id` (your SKU). Safe to call repeatedly. Catalog changes reach the recommendations immediately.
```json
{ "product_id": "SKU-1", "name": "Acme Pro Laptop", "category": "Laptops", "brand": "Acme",
  "price": 59999, "rating": 4.5, "tags": ["trending"], "is_active": true, "in_stock": true,
  "description": "...", "image_url": "https://...", "attributes": {"color": "silver"} }
```
Bulk body: `{ "products": [ ... ] }` -> `{ "created": 2, "updated": 1, "total": 3 }`. Duplicate ids inside one request: last one wins.
Inactive (`is_active=false`) or out-of-stock products are never recommended.

### GET /products
Query: `q` (name / SKU / brand), `category`, `brand`, `in_stock`, `include_inactive`, `sort` (`name|price|rating|created`),
`order` (`asc|desc`), `page`, `page_size` (max 100). Returns `{ items, total, page, page_size, total_pages }`.

### GET /products/filters  -  distinct categories and brands.
### GET /products/{product_id}  -  one product (`404 PRODUCT_NOT_FOUND`).

## Recommendations

The **serving** endpoints are open like `/events` (called by your storefront; protect at network level until API-key auth
exists). `limit` is 1-50 (default 10). Every item carries a human-readable `reason` and the `algorithm` that produced it.

| Endpoint | What it returns |
|---|---|
| `GET /recommendations/popular?category=` | Trending products (time-decayed, weighted by view / wishlist / cart / purchase) |
| `GET /recommendations/similar/{product_id}` | Content similarity (category, brand, tags, price band, name) blended with collaborative filtering |
| `GET /recommendations/frequently-bought/{product_id}` | Products purchased in the same session (min. support 2), falls back to "popular with similar shoppers" |
| `GET /recommendations/user/{external_user_id}` | Personalised hybrid; a customer without history gets `popular` (`personalized: false`) |
| `GET /recommendations/home/{external_user_id}` | Home-page rows: *Recommended for you*, *Trending now*, *Popular in <favourite category>* |
| `POST /recommendations/track` | Record an `impression` or `click` (stored as `RECOMMENDATION_VIEW` / `RECOMMENDATION_CLICK` events; feeds CTR) |

```json
{ "success": true, "data": { "algorithm": "hybrid", "personalized": true, "count": 2, "generated_at": "...",
  "items": [ { "product_id": "PROD_1127", "name": "...", "category": "Furniture", "brand": "Apple", "price": 4999.0,
               "rating": 4.4, "in_stock": true, "score": 0.5774, "algorithm": "collaborative",
               "reason": "Customers who liked Adidas Radio Sock also liked this" } ] } }
```
Track body: `{ "external_user_id": "U1", "product_id": "P1", "action": "impression" | "click", "algorithm": "hybrid", "session_id": "...", "idempotency_key": "..." }`.

Admin endpoints (logged-in user): `GET /recommendations/status` (model size, build time, usage per algorithm) and
`POST /recommendations/refresh` (**ADMIN**: rebuild the model now).

How it works: the model is an in-memory snapshot built from the last `RECO_LOOKBACK_DAYS` (90) of events and the catalog,
rebuilt after `RECO_SNAPSHOT_TTL_SECONDS` (300) or when a product changes. Interactions decay with a
`RECO_HALF_LIFE_DAYS` (30) half-life.

## Customers (Phase 3)

All customer endpoints need a logged-in user (they contain personal behaviour data); recompute needs `ADMIN`/`SUPER_ADMIN`.
Profiles are rebuilt from the event stream every `CUSTOMER_PROFILE_REFRESH_MINUTES` (60) and on demand.

**How money is measured.** Events carry no price, so a `PURCHASE` is worth, in this order:
1. `metadata.amount` - the line total, used as-is
2. `metadata.price` (or the catalog price of `product_id`) x `metadata.quantity` (default 1)

`RETURN` / `PURCHASE_CANCELLED` events subtract the same value. One **order** = one `session_id` (or one calendar day
when no session id is sent), so send the same `session_id` for all items bought together.

| Endpoint | What it returns |
|---|---|
| `GET /customers` | Paginated list. Query: `q` (id), `segment`, `sort` (`last_seen|spend|orders|recency|events|rfm`), `order`, `page`, `page_size` (max 100) |
| `GET /customers/{id}` | Full profile: stats, RFM, segment (with description + suggested action), favourite category/brand |
| `GET /customers/{id}/timeline` | Behaviour timeline, newest first (`page`, `page_size`) with product names |
| `GET /customers/stats` | Customers, buyers, repeat rate, revenue, average order value, top spenders |
| `POST /customers/recompute` | **ADMIN.** Recompute profiles, RFM and segments now. `409 RECOMPUTE_IN_PROGRESS` if one is already running |

```json
{ "customer_id": "USER_10005", "segment": {"key": "champions", "name": "Champions"},
  "stats": { "orders": 4, "total_spend": 497884.51, "avg_order_value": 124471.13, "recency_days": 3,
             "events": 40, "views": 20, "cart_adds": 6, "items_purchased": 5, "returns": 0 },
  "rfm": { "r": 5, "f": 4, "m": 5, "code": "545" }, "favorite_category": "Laptops", "favorite_brand": "Acme" }
```

## Segments (Phase 3)

### GET /segments
All 12 segments (also empty ones) with `customers`, `share`, `revenue`, `revenue_share`, `avg_spend`, `avg_recency_days`,
`avg_orders`, the definition (`description`, suggested `action`), and `rfm_grid` (buyer counts per Recency x Frequency cell).
### GET /segments/{key}  -  one segment (`404 SEGMENT_NOT_FOUND`).

| Key | Meaning |
|---|---|
| `champions` | Recent, frequent, high-spend buyers |
| `loyal` | Regular buyers |
| `potential_loyalist` | Recent buyers not yet frequent |
| `new_customer` | First order within the last `CUSTOMER_ACTIVE_DAYS` days |
| `need_attention` | Above-average buyers going quiet |
| `about_to_sleep` | Below-average recency and frequency |
| `cant_lose` | Former top customers who went quiet |
| `at_risk` | Frequent buyers who have not returned |
| `hibernating` / `lost` | Low / lowest recency and frequency |
| `prospect` | Active recently, never purchased |
| `inactive` | Never purchased, not seen recently |

Scoring: **Recency** and **Monetary** are percentile-ranked 1-5 among buyers (5 = best); **Frequency** uses fixed bins
(1 order = 1, 2 = 2, 3 = 3, 4-5 = 4, 6+ = 5). The RFM code is `RFM`, e.g. `545`.

## Offers (Phase 4)

An offer is a coupon campaign: a **code**, a **discount**, **who** may use it (customer segments / categories) and **guardrails**.

| Field | Meaning |
|---|---|
| `code` | Coupon code, unique, stored in upper case (3-64 chars: `A-Z 0-9 _ -`). Cannot change after creation |
| `offer_type` | `percent_off` (value 1-100), `fixed_off` (value > 0), `free_shipping` (value ignored) |
| `max_discount` | Cap on the discount per order (empty = no cap) |
| `min_order_value` | Order must be at least this much (empty = none) |
| `max_redemptions` | Total budget of redemptions (empty = unlimited) |
| `max_per_customer` | How many times one customer may redeem it (default 1) |
| `starts_at`, `ends_at` | Optional schedule (**timezone required**) |
| `target_segments` | Segment keys (see Segments). Empty = every customer. Customers who are not scored yet only see offers without segment targeting |
| `target_categories` | Empty = any. When set, checkout must send matching `categories` |
| `priority` | 0-100, used when ranking |

**Lifecycle:** a new offer is a `draft`. `draft → active`, `active ⇄ paused`, `draft/active/paused → ended` (final).
`effective_status` also reports `scheduled` (before `starts_at`) and `expired` (after `ends_at`) - these are derived, not stored.

### Storefront (no login, like `/events`)

`GET /offers/user/{external_user_id}?limit=5&category=Laptops&cart_value=2500` returns the offers this customer can use right now,
best first, each with a `reason` (e.g. *Made for Champions*, *Matches your interest in Laptops*, *Ends in 2 days*), a `score`,
and a `discount_preview` when `cart_value` is sent. Ranking blends segment fit, category interest, discount value, priority,
urgency and the offer's observed conversion.

`POST /offers/track` - `{ "code": "WELCOME10", "external_user_id": "U1", "action": "impression" | "click", "idempotency_key": "..." }`
records an impression or click (also added to the customer's timeline as `OFFER_VIEW` / `OFFER_CLICK`).

### Checkout (login required: `ADMIN`, `SUPER_ADMIN` or `MARKETING_MANAGER` - use a service account, see below)

`POST /offers/validate` - `{ "code": "VIP15", "external_user_id": "U1", "order_value": 2500, "categories": ["Laptops"] }`
returns HTTP 200 with `valid: true` and `discount_amount`, `free_shipping`, `final_value`, or `valid: false` with a `reason_code`:
`OFFER_NOT_FOUND, NOT_ACTIVE, NOT_STARTED, EXPIRED, NOT_ELIGIBLE, LIMIT_REACHED, CUSTOMER_LIMIT_REACHED, MIN_ORDER_NOT_MET, CATEGORY_NOT_MATCHED`
plus a human readable `reason`.

`POST /offers/redeem` - same body plus `"order_id": "ORD-1001"`. Call it when the order is placed. It re-checks everything and records
the redemption atomically, so concurrent checkouts can never exceed the budget or the per-customer limit. Sending the same `order_id`
again returns the original result with `duplicate: true` (safe to retry). A redemption is also recorded as an `OFFER_REDEEM` event.

### Admin (read: any logged-in user; write: `ADMIN`, `SUPER_ADMIN`, `MARKETING_MANAGER`)

| Endpoint | Purpose |
|---|---|
| `GET /offers` | List with performance. Query: `status`, `q` (name/code), `sort` (`created|name|priority|ends`), `page`, `page_size` (max 100) |
| `GET /offers/{id}` | One offer with `stats`: impressions, clicks, ctr, redemptions, redemption_rate, discount_given, revenue, remaining |
| `POST /offers` | Create (starts as `draft`) |
| `PUT /offers/{id}` | Edit (not the code; ended offers cannot be edited) |
| `POST /offers/{id}/status` | `{ "status": "active" | "paused" | "ended" }` |
| `GET /offers/stats` | Counts by status, `active_now`, all-time and 30-day totals |

### Service accounts

There is no sign-up endpoint. Create users from the command line (inside Docker prefix with `docker compose exec backend`):
```
python -m scripts.create_user --email shop@yourstore.com --password 'a-long-password' --role ADMIN --name "Store backend"
python -m scripts.create_user --email maya@yourstore.com --password '...' --role MARKETING_MANAGER
python -m scripts.create_user --email shop@yourstore.com --password 'new-password' --role ADMIN --update
```
Roles: `SUPER_ADMIN`, `ADMIN`, `MARKETING_MANAGER`, `VIEWER` (read-only).

## Experiments / A/B tests (Phase 6)

An experiment compares **variants** on one **surface**:

| `kind` | What a variant changes | Variant `config` |
|---|---|---|
| `recommendations` | The strategy behind `GET /recommendations/user/{id}` | `{ "strategy": "hybrid" \| "content" \| "collaborative" \| "popular" }` |
| `offers` | Which offers `GET /offers/user/{id}` may show | `{}` = all offers (normal), `{ "offer_codes": [] }` = none (holdout), `{ "offer_codes": ["VIP15"] }` = only these |

The **first variant is the control**. `traffic_percent` (1-100) is the share of customers that take part; `weight` splits them between variants.
`primary_metric` is `conversion` (bought after exposure), `click` (clicked a recommendation / offer) or `revenue` (revenue per customer).

**Nothing to integrate:** the first time your site calls the serving endpoint for a customer, the customer is assigned (stable hashing, same answer
every time), an exposure is stored, and the response contains `"experiment": { "id", "key", "variant" }` (or `null`). Outcomes (purchases, clicks) are
counted from that moment, only for exposed customers. Calls from customers outside the traffic share behave normally.

| Endpoint | Purpose |
|---|---|
| `GET /experiments` | List (`status`, `kind`, `q`, `page`, `page_size`) with exposed customer counts |
| `GET /experiments/{id}` | One experiment |
| `GET /experiments/{id}/results` | Per-variant numbers, comparison against the control and a verdict (below) |
| `GET /experiments/{id}/assign/{external_user_id}` | Which variant this customer would get (records nothing) |
| `GET /experiments/stats` | Counts by status, running experiments, customers in tests |
| `POST /experiments` | Create as `draft` (`ADMIN`, `SUPER_ADMIN`, `MARKETING_MANAGER`) |
| `PUT /experiments/{id}` | Edit - **drafts only** |
| `POST /experiments/{id}/status` | `{ "status": "running" \| "paused" \| "completed", "winner_key": "b" }` (winner optional, only when completing) |

```json
{ "key": "homepage-reco", "name": "Hybrid vs content", "kind": "recommendations", "primary_metric": "conversion", "traffic_percent": 50,
  "variants": [ { "name": "Hybrid (current)", "config": { "strategy": "hybrid" } },
                { "name": "Content only", "key": "content", "weight": 1, "config": { "strategy": "content" } } ] }
```

**Lifecycle:** `draft → running ⇄ paused → completed` (final). Only **one running experiment per kind** (`409 EXPERIMENT_KIND_BUSY`).
Starting an offers experiment checks that every referenced offer code exists (`422 UNKNOWN_OFFER_CODE`). Paused / completed experiments stop assigning.

**Results.** For each variant: exposed `customers`, `conversions` / `conversion_rate`, `clickers` / `click_rate`, `revenue_total`,
`revenue_per_customer`. Each non-control variant has `comparisons` for `conversion` and `click` (two-proportion z-test) and `revenue` (Welch t-test):
`control`, `variant`, `diff`, `lift`, `p_value`, `ci_low`, `ci_high`, `significant` (p < 0.05). `verdict.status`:
`collecting` (a variant has fewer than 30 exposed customers), `winner`, `control_better`, `inconclusive` (with the sample size needed per variant
to detect a 10 % lift). Revenue is valued like customer spend (see Customers).

## Users (admin: `ADMIN`, `SUPER_ADMIN`)

| Endpoint | Purpose |
|---|---|
| `GET /users` | All staff users (never returns passwords) |
| `POST /users` | `{ "email", "password" (8+ chars), "full_name", "role" }` |
| `PATCH /users/{id}` | Change any of `full_name`, `role`, `is_active`, `password` (send at least one) |

Rules: only a `SUPER_ADMIN` may create, grant, change or deactivate `SUPER_ADMIN` accounts (`403 INSUFFICIENT_ROLE`);
nobody can change their own role or deactivate themselves (`409 CANNOT_MODIFY_SELF`); there is always one active Super Admin
(`409 LAST_SUPER_ADMIN`); duplicate email is `409 EMAIL_ALREADY_EXISTS`. Disabling a user, changing their role or password ends their
sessions immediately (access tokens are rejected, refresh tokens revoked).

## Search

`GET /search?q=alpha&limit=5` (logged-in, `q` needs 2+ characters) returns `customers` (id + segment), `products` (id, name, category)
and `offers` (id, code, name, status). Case-insensitive contains-match; `%` and `_` are treated literally.

## Integrations and System

`GET /integrations/status` (logged-in) - what the shop is sending: event counts (24 h / 7 d / total), last event time, catalog size,
data quality (share of product events with unknown product ids, purchases without `session_id`), recommendation and checkout usage,
a `checklist` (`ok` / `warning` / `todo` per step) and a `score` (0-1). Admins also get the list of `accounts`.

`GET /system/status` (admin) - app version, uptime, database health (latency, size, version, current migration, row count per table),
Redis health, background-job settings and last run, recommendation model status, and the non-secret active settings.

`GET /system/alerts` (logged-in) - `{ count, needs_attention, items: [{ id, severity: critical|warning|info, title, message, link }] }`.
Alerts: Redis down, no events yet / none in 24 h, no products, > 30 % out of stock, customer segments missing or stale, offers that ended
but are still active, ending within 3 days, or with 90 % of the budget used.

## Analytics

### GET /analytics/report?days=30  (logged-in user)
One call for the Analytics screen: the last `days` (1-365) compared with the same number of days before.
`kpis` (revenue, orders, avg_order_value, active_customers, new_customers, conversion_rate, events - each `{ value, previous, change }`),
`daily` series (events, active/new customers, orders, revenue, recommendation views/clicks/served, offer impressions/clicks/redemptions/discount),
`funnel` (distinct customers: viewed → carted → checkout → purchased), `top_products`, `top_categories` (net revenue after returns), `platforms`.
Revenue is valued like customer spend (see Customers): `amount`, else `price x quantity`, else the catalog price.

### GET /analytics/overview  (logged-in user)
Totals (customers, products, events, purchases, recommendations served), recommendation CTR (30 days), events per day
(14 days), events by type and top categories (30 days). Feeds the Flutter dashboard.

## Error Codes

| HTTP Status | code | Meaning |
|---|---|---|
| 401 | `INVALID_CREDENTIALS` | Wrong email/password on login |
| 401 | `INVALID_ACCESS_TOKEN` | Missing, malformed, or expired access token |
| 401 | `INVALID_REFRESH_TOKEN` | Refresh token invalid or expired |
| 401 | `REFRESH_TOKEN_REVOKED` | Refresh token was already rotated/logged out |
| 403 | `FORBIDDEN` | Your role is not allowed to do this (e.g. a VIEWER writing products) |
| 404 | `PRODUCT_NOT_FOUND` | Product id is not in the catalog |
| 404 | `CUSTOMER_NOT_FOUND` / `SEGMENT_NOT_FOUND` | Unknown customer id / segment key |
| 409 | `RECOMPUTE_IN_PROGRESS` | Another customer-profile recompute is running |
| 409 | `CODE_ALREADY_EXISTS` | An offer with this code already exists |
| 409 | `INVALID_TRANSITION` / `OFFER_ENDED` | Offer status change not allowed / editing an ended offer |
| 404 | `OFFER_NOT_FOUND` | No offer with this id or code (track) |
| 404 | `USER_NOT_FOUND` / `EXPERIMENT_NOT_FOUND` | No user / experiment with this id |
| 409 | `EXPERIMENT_KEY_EXISTS` / `EXPERIMENT_KIND_BUSY` / `EXPERIMENT_NOT_DRAFT` | Duplicate key / another test is running for that surface / editing a non-draft |
| 422 | `KEY_IMMUTABLE` / `UNKNOWN_VARIANT` / `UNKNOWN_OFFER_CODE` | Experiment key changed on edit / winner is not a variant / offer code does not exist |
| 403 | `INSUFFICIENT_ROLE` | Only a Super Admin may manage Super Admin accounts |
| 409 | `CANNOT_MODIFY_SELF` / `LAST_SUPER_ADMIN` / `EMAIL_ALREADY_EXISTS` | See the Users section |
| 422 | `CODE_IMMUTABLE` / `OFFER_ALREADY_EXPIRED` | Offer code changed on edit / activating an offer whose `ends_at` has passed |
| 422 | `INVALID_SEGMENT` | `segment` filter is not one of the 12 keys |
| 422 | `VALIDATION_ERROR` | Request failed validation; `error.details` lists each field |
| 500 | `INTERNAL_SERVER_ERROR` | Unexpected server error — safe to retry with backoff |

## Coming in Later Phases

- Advanced ML models (ranking, churn, purchase probability) - Phase 7
- Event/recommendation/offer service-to-service auth (API key or mTLS) - before production go-live
