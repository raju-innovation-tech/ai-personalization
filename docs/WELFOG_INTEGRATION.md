# Welfog integration

How the AI engine gets Welfog's data and how Welfog uses the engine.

```
Welfog MySQL / Postgres ──(read-only)──► scripts/welfog_sync ──► engine API ──► engine's OWN PostgreSQL
Welfog website / app ── live events + impressions/clicks ─────────────────────►  (never Welfog's database)
Welfog backend ◄── recommendations / offers ──────────────────────────────────  engine API
```

The engine keeps its own database (`ai_personalization`). Welfog's databases are only ever **read**.

## 1. Data facts (checked against the real dumps)

| Topic | Fact |
|---|---|
| Customer id | `orders.user_id`, `carts.user_id`, `wishlists.user_id` = `customers.user_id` (not `customers.id`, not always `users.id`) |
| Product id | Those tables hold Postgres `products.pro_id` (not `products.id`) -> engine `product_id` |
| Catalogue | Postgres `products` (partitioned by quarter). `unit_price` is text. Brand is "No Brand"/"Non-Branded"/blank for most rows, `tags` empty, `rating` almost empty |
| Orders | One row per purchased line. `price` = line total (`sp_price * quantity`); `grand_total = price + shipping_cost*qty + tax - coupon_discount - coin_discount` |
| Order outcome | Most rows are unpaid COD orders that were auto-cancelled (never completed) |
| Baskets | `combined_order_id` and `shipment_id` are empty, so there is no basket id |
| Timestamps | Naive (no timezone). **Confirm the timezone with Welfog** (`WELFOG_SOURCE_TZ`) |

## 2. Mapping rules (`app/integrations/welfog/mapping.py`)

| Welfog | Engine | Rule |
|---|---|---|
| `products` row | `POST /products/bulk` | `product_id = pro_id`; `price = float(unit_price)`; `category = category_name`; placeholder brands -> none (so unbranded items are not "similar" to each other); `is_active = published AND approved AND NOT hold AND NOT block`; `in_stock = stock > 0`; HTML stripped from description; relative image path joined to `WELFOG_IMAGE_BASE_URL` |
| `orders`, not cancelled | `PURCHASE` | `amount = price - coupon_discount - coin_discount` (never below 0), `quantity`, `order_id`; shipping is **not** counted as spend |
| `orders`, cancelled **and paid** | `PURCHASE` + `PURCHASE_CANCELLED` | the refund nets the customer's spend back to zero |
| `orders`, cancelled **and unpaid** | nothing | checkout never completed |
| `orders`, `return_status = Completed` | extra `RETURN` | `Canceled` return requests are ignored |
| `carts` | `ADD_TO_CART` | guest rows (no `user_id`) are skipped |
| `wishlists` | `WISHLIST_ADD` | |
| `reviews` | `PRODUCT_REVIEW` | `user_id = 0` (anonymous) rows are skipped |
| `user_events` (new table) | the same `event_type` | see section 4 |

* All timestamps are sent as UTC. Every event has a stable idempotency key (`welfog:order:<oid>:purchase`, ...), so re-running a sync never duplicates data.
* One checkout basket = same customer + same minute (`session_id = basket:<user>:<yyyymmddHHMM>`), unless `orders.session_id` is filled by Welfog.

## 3. Running the sync

1. Install: `pip install -r requirements.txt` (adds PyMySQL, tzdata).
2. Ask Welfog for **read-only** DB users, set the `WELFOG_*` and `AI_ENGINE_*` variables (see `.env.example`).
3. Create the service account: `python -m scripts.create_user --email ai-sync@yourcompany.com --password '...' --role ADMIN`
4. `python -m scripts.welfog_sync --dry-run` - reads and maps everything, sends nothing; check the printed counts.
5. `python -m scripts.welfog_sync --sources products` then `python -m scripts.welfog_sync` for the rest.
6. Schedule it (cron every 10-15 minutes). It resumes from `welfog_sync_state.json`; a failed send never advances the saved position. `--full` starts over (safe, idempotent).

Expected output on the Welfog sample dumps: 1010 products; 150 PURCHASE, 41 PURCHASE_CANCELLED, 2 RETURN, 260 ADD_TO_CART, 82 WISHLIST_ADD, 8 PRODUCT_REVIEW events.

## 4. What Welfog must add on their side

* **`docs/welfog_mysql_tracking.sql`** - the `user_events` table, `session_id`/`platform` columns, and triggers for cart-add / wishlist add+remove. Run on staging first.
* Their app/backend must **insert** `PRODUCT_VIEW`, `CATEGORY_VIEW`, `PRODUCT_SEARCH`, `CHECKOUT_STARTED`, `REMOVE_FROM_CART` rows (section 4 of that file) and fill `orders.session_id` / `orders.platform`.
* After running the triggers, set `WELFOG_EVENTS_TABLE_START` (UTC, with `+00:00`) to that moment.
* Alternative to the table: Welfog posts the same events straight to `POST /events/batch`. Use one route, not both.

## 5. Engine API Welfog calls (base `/api/v1`)

| Call | Auth today | Use |
|---|---|---|
| `GET /recommendations/home/{user_id}` , `/user/{user_id}` , `/similar/{pro_id}` , `/frequently-bought/{pro_id}` , `/popular` | none | show recommendations |
| `POST /recommendations/track` | none | `{"external_user_id","product_id","action":"impression"\|"click","algorithm","session_id"}`; copy `algorithm` from the item |
| `GET /offers/user/{user_id}` , `POST /offers/track` | none | show offers; impression / click |
| `POST /offers/validate` , `POST /offers/redeem` | **login, role ADMIN / SUPER_ADMIN / MARKETING_MANAGER** | checkout; `redeem` needs `order_id`. Call from Welfog's backend with a service-account token |
| `POST /events` , `/events/batch` | none | behaviour events (alternative to `user_events`) |
| `POST /products/bulk` | login, ADMIN | catalogue (done by the sync) |

`product_id` is always the Postgres `pro_id`; `user_id` is `customers.user_id`.

## 6. Known limits - read before going live

* `/events`, `/recommendations/*`, `/offers/user|track` have **no authentication** yet. Put them on a private network or add API-key auth first.
* Recommendation quality depends on view/click data. Purchases in the sample are tiny (122 of 150 have a grand total under ₹7, which looks like test orders; only a handful of real buyers); expect popularity/category based results until live traffic data arrives.
* Guest carts (`temp_user_id`) cannot be attributed to a customer and are skipped.
* Some cart/review rows point at products that are not in the live `products` table (e.g. only in `single_products`); the engine cannot use them for recommendations.
* The timezone of Welfog's timestamps must be confirmed; a wrong `WELFOG_SOURCE_TZ` shifts every event.
* `orders` and `products` are paged by `COALESCE(updated_at, created_at)`. On a very large live table this needs an index
  on `updated_at`; ask Welfog for one (or run the first full sync off-peak / from a read replica).
* The sync's database wiring (MySQL/Postgres connections) and the real HTTP calls need a live environment to try:
  run `--dry-run` against a staging copy first.
