# Architecture

## Components

```
E-commerce platform ──events──▶  FastAPI backend ──▶ PostgreSQL (events, customers, products, users)
                    ◀──recs/offers──   │  │
                                       │  └──▶ Redis (cache, Celery broker/result)
                                       └──▶ Celery worker (background jobs, Phase 3+)
Flutter Admin (Web/Windows/Android) ──JWT──▶ FastAPI backend
```

## Backend layout

| Path | Responsibility |
|---|---|
| `app/main.py` | App factory, CORS, request-id/logging middleware, error envelope handlers |
| `app/core/` | Settings, security (Argon2 + JWT), structured logging, response envelope, health |
| `app/database/` | Async engine/session, ORM models, Alembic migrations |
| `app/auth/` | Login / refresh (rotating, hashed) / logout / `me`, RBAC dependencies |
| `app/events/` | Event ingestion: single + batch, race-safe idempotency |
| `app/products/` | Catalog sync (race-safe bulk upsert) + admin listing |
| `app/recommendations/` | `engine.py` (pure-Python models, unit-testable), `service.py` (SQL loading + snapshot cache), `router.py` |
| `app/customers/` | `intelligence.py` (pure RFM + segment rules), `service.py` (SQL aggregation, profile upsert, queries), `scheduler.py` (hourly refresh) |
| `app/segments/` | Segment definitions (names, descriptions, suggested actions) and the segments API |
| `app/offers/` | `engine.py` (pure eligibility / discount / ranking), `service.py` (SQL, redemption locking, tracking), `router.py` |
| `app/experiments/` | `engine.py` (hash assignment, z-test / Welch test, sample size, verdict - pure), `service.py` (serving-time assignment, lifecycle, results), `router.py` |
| `app/analytics/` | Dashboard overview numbers (`router.py`) and the period report with comparison, funnel and top lists (`report.py`) |
| `app/integrations/` | Setup checklist + data-quality checks for the shop integration |
| `app/system/` | System status for admins and the alert rules behind the notification bell |
| `app/users/` | Staff user management with role rules (shared by the API and `scripts/create_user.py`) |
| `app/search/` | Global search across customers, products and offers |
| `app/workers/` | Celery app |

## Key design decisions

- **Idempotent ingestion in the database.** Duplicate events are rejected by
  `INSERT ... ON CONFLICT DO NOTHING` on the unique `idempotency_key`, so concurrent retries
  never return 500 and never double-count.
- **One error envelope** for every failure (including 404/405/422):
  `{"success": false, "error": {"code", "message", "details?"}}`.
- **Rotating refresh tokens**, stored as SHA-256 hashes; refresh is serialized with
  `SELECT ... FOR UPDATE` so one token can be redeemed only once.
- **Tests use a separate `<db>_test` database** (auto-created, enforced in `tests/conftest.py`),
  never the development database.

## Recommendation engine

`Snapshot` (in `engine.py`) is an immutable in-memory model built from the catalog plus event aggregates
(`SUM(weight * exp(-ln2 * age / half_life))` computed in SQL):

| Strategy | Signal |
|---|---|
| Popularity | Weighted, time-decayed interactions (purchase 8, cart 4, wishlist 3, view 1; cancel/return negative) |
| Content-based | TF-IDF cosine over category, brand, tags, price band, colour, name tokens (inverted index) |
| Collaborative | Item-item cosine over the user x item matrix, shrunk when few customers overlap |
| Bought together | Purchases in the same session; score = support / sqrt(count(A) * count(B)); min support 2 |
| Hybrid (per customer) | 0.5 collaborative + 0.3 content + 0.2 popularity over the customer's top-10 items; excludes purchased items; max ~1/3 per category; cold start -> popular |

Items that are inactive, out of stock or unknown to the catalog are never returned. The snapshot is cached per process
(`RECO_SNAPSHOT_TTL_SECONDS`), invalidated when the catalog changes, and rebuilt in a worker thread so requests are never blocked.

## Customer intelligence

Customer profiles live as extra columns on `ecommerce_customers` (one row per `external_user_id`). `recompute_profiles`:

1. loads the last `CUSTOMER_LOOKBACK_DAYS` (365) of events with a handful of grouped SQL queries (behaviour counters,
   purchases, refunds, favourite category/brand),
2. values every purchase (`metadata.amount`, else `price x quantity`, else the catalog price), groups items into orders
   by session, subtracts returns/cancellations,
3. scores buyers: Recency and Monetary by percentile rank, Frequency by fixed bins, then applies the first matching
   segment rule (non-buyers become `prospect` / `inactive`),
4. upserts all profiles in chunks inside one transaction guarded by a PostgreSQL advisory lock, so two workers (or a
   worker plus a manual click) never recompute at the same time.

`scheduler.py` re-runs this every `CUSTOMER_PROFILE_REFRESH_MINUTES` from the API process (set `0` to disable).

## Offer engine

* **Eligibility** (`check_eligibility`) is one ordered rule list used by serving, validate and redeem, so they can never disagree:
  schedule/status → segment → total budget → per-customer limit → minimum order → category.
* **Ranking** = 0.35 relevance (segment fit, category interest) + 0.25 discount value + 0.20 priority + 0.10 urgency
  (rises in the last 7 days) + 0.10 observed conversion `(redemptions+1)/(impressions+20)`.
* **Redeem** runs in one transaction: `SELECT ... FOR UPDATE` on the offer row serialises concurrent redemptions, then
  limits are re-checked, the redemption row is inserted (unique `(offer, order_ref)` makes retries idempotent) and an
  `OFFER_REDEEM` event is recorded. Budgets therefore cannot be exceeded under load.
* Segments come from the Phase 3 profiles, so an offer reaches a customer only after that customer has been scored
  (hourly, or press **Recompute**).

## A/B testing

* **Assignment is stateless:** `sha256(experiment_key#traffic + customer)` decides whether the customer takes part and a second hash
  (`#variant`) decides which variant (weights respected). Same customer, same answer, forever; raising the traffic share only adds customers.
* **Exposure is stored once** (`INSERT .. ON CONFLICT DO NOTHING` on `(experiment, customer)`) when the serving endpoint first answers that
  customer, so concurrent first requests cannot double count.
* **Results** count only events after the customer's first exposure (and before the experiment ended): purchases (valued like customer spend),
  recommendation clicks or offer clicks. Conversion and click rate use a two-proportion z-test against the control, revenue per customer a Welch
  t-test, both reported with p-values and 95 % intervals. A variant needs 30 exposed customers before any verdict is given.
* **Serving hooks:** `GET /recommendations/user/{id}` swaps the strategy of `Snapshot.for_user`; `GET /offers/user/{id}` filters the candidate offers.
  One running experiment per surface keeps the two tests from contaminating each other.

## Admin dashboard (Flutter)

`lib/features/<feature>/{domain,data,presentation}` per area; `core/` holds the API client (token refresh), routing, theme and formatters.
Riverpod providers load data; GoRouter shell provides the sidebar (role-aware), top bar (search, alerts, theme) and mobile drawer.
Alerts refresh every 2 minutes. The theme choice is stored with the same secure storage package as the login tokens.

## Security notes

- `/events`, `/recommendations/*` and the storefront offer endpoints (`/offers/user`, `/offers/track`) are not authenticated (see `API.md`) - protect it at the network layer
  until service-account/API-key auth is added.
- Change `JWT_SECRET_KEY` and `FIRST_SUPER_ADMIN_PASSWORD` before any shared deployment.
