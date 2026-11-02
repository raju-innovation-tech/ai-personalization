# AI Personalization & Offer Engine

A backend + admin dashboard that plugs into an existing e-commerce platform. Your shop sends **events** (views, cart adds,
purchases) and **products**; the engine learns from them and gives back **recommendations**, **customer profiles**,
**segments**, **personalised offers (coupons)** and **A/B tests** that show which of them really works. A Flutter admin app (Web / Windows / Android) shows everything.

| Phase | What it adds | Status |
|---|---|---|
| 1 | Login (JWT + roles), event ingestion, health checks, Docker, Flutter shell | ✅ done |
| 2 | Product catalog API, recommendations (popular, similar, bought-together, personalised), CTR tracking | ✅ done |
| 3 | Customer profiles, RFM scoring, 12 customer segments, customer timeline | ✅ done |
| 4 | Offer engine: coupons targeted at segments, guardrails, checkout validate/redeem, performance tracking | ✅ done |
| 5 | Complete admin dashboard: Analytics, Integrations, System, Users, global search, alerts, dark mode | ✅ done |
| 6 | A/B testing of recommendations and offers with statistical results | ✅ done |
| 7+ | Advanced ML, production hardening | ⏳ see `docs/ROADMAP.md` |

**Contents:** [1 What you get](#1-what-you-get) · [2 Architecture](#2-architecture) · [3 What to install](#3-what-to-install-on-your-pc) ·
[4 Libraries](#4-libraries-and-packages-what-and-why) · [5 Setup, step by step](#5-setup-step-by-step) · [6 Run the app](#6-run-the-flutter-app-on-every-platform) ·
[7 Tour](#7-using-the-app) · [8 Configuration](#8-configuration-reference) · [9 Connect your shop](#9-connect-your-own-shop-data) ·
[10 Tests](#10-tests-and-code-checks) · [11 Troubleshooting](#11-troubleshooting) · [12 Project layout](#12-project-layout) · [13 Security](#13-security-and-going-to-production)

---

## 1. What you get

**Backend (FastAPI + PostgreSQL + Redis)**
- `POST /events`, `POST /events/batch` - idempotent event ingestion (safe to retry, safe under concurrency)
- `POST /products`, `POST /products/bulk`, `GET /products` - catalog sync and browsing
- `GET /recommendations/popular | similar/{id} | frequently-bought/{id} | user/{id} | home/{id}`, `POST /recommendations/track`
- `GET /customers`, `/customers/{id}`, `/customers/{id}/timeline`, `/customers/stats`, `POST /customers/recompute`
- `GET /segments` - 12 RFM segments with size, revenue, suggested action, RFM grid
- `GET /offers/user/{id}` (storefront) · `POST /offers/validate`, `/offers/redeem` (checkout) · `POST /offers/track` · offer CRUD + lifecycle + performance
- `GET /analytics/report?days=30` - period report with comparison, funnel, top products · `GET /analytics/overview`
- `GET/POST /experiments`, `/experiments/{id}/results`, `/experiments/{id}/status` - A/B tests with significance and a verdict
- `GET /integrations/status` · `GET /system/status` · `GET /system/alerts` · `GET /search?q=` · `GET/POST/PATCH /users`
-  `/health`, `/ready`
- Full reference: [`docs/API.md`](docs/API.md) - interactive Swagger at http://localhost:8000/docs

**Flutter admin app:** Login · Experiments (A/B tests) · Analytics · Integrations (setup checklist) · System · Users · global search, alerts bell, dark mode · Offers (create / edit / activate / pause / end, performance, playground) · Dashboard (KPIs, charts, segment chart) · Customers (search, filter, detail with RFM, recommendations,
timeline) · Segments (RFM heat-map + cards) · Products (search, filter, per-product recommendations) · Recommendation Engine (status + playground).

## 2. Architecture

```
 Your e-commerce site ──events / products──▶ ┌───────────────────────────┐
                      ◀── recommendations ───│  FastAPI backend (:8000)  │──▶ PostgreSQL (:5432)
                                             │  auth · events · products │──▶ Redis (:6379)
 Flutter admin app ──── JWT (login) ────────▶│  recommendations          │
 (Chrome / Windows / Android)                │  customers · segments     │     Celery worker + Flower (:5555)
                                             └───────────────────────────┘     (installed, used from later phases)
```
More detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## 3. What to install on your PC

You only need the **required** row(s) for the path you choose. Path A (Docker) is the easiest and what this guide assumes.

| Tool | Needed for | Required? | Get it |
|---|---|---|---|
| **Docker Desktop** (includes Compose v2) | Runs PostgreSQL, Redis, the API, the worker | **Yes** for Path A | https://www.docker.com/products/docker-desktop - open it once and wait until it says "running" |
| **Flutter SDK 3.27 or newer** (Dart 3.6+) | The admin app | **Yes** | https://docs.flutter.dev/get-started/install - then run `flutter doctor` |
| **Google Chrome** | Easiest way to run the admin app (`-d chrome`) | Recommended | https://www.google.com/chrome |
| **Visual Studio 2022/2026** with *Desktop development with C++* | Only for `flutter run -d windows` | Optional | If the build fails on `atlstr.h`, also tick **"C++ ATL for latest build tools"** in Visual Studio Installer |
| **Android Studio** + Android SDK | Only for Android emulator / phone | Optional | https://developer.android.com/studio (then `flutter doctor --android-licenses`) |
| **Git** | Only if you clone instead of unzipping | Optional | https://git-scm.com |
| Python 3.12, PostgreSQL 16, Redis 7 | Only for **Path C** (no Docker) | Optional | python.org, postgresql.org, redis.io (Windows: Memurai or WSL) |

Check your install (all should print a version / "No issues found"):
```powershell
docker --version
docker compose version
flutter --version
flutter doctor
```

## 4. Libraries and packages: what and why

> Phases 3 and 4 added **no new packages** - everything below is all you ever need to install.

You do **not** install these by hand. Docker installs the backend ones from `backend/requirements.txt`; `flutter pub get`
installs the Flutter ones from `flutter_admin/pubspec.yaml`.

**Backend (Python 3.12) - `backend/requirements.txt`**

| Package | Why it is here |
|---|---|
| `fastapi`, `uvicorn[standard]` | The web framework and server |
| `sqlalchemy` (async), `asyncpg`, `psycopg2-binary` | Database access (asyncpg for the API, psycopg2 for Alembic and tests) |
| `alembic` | Database migrations (`alembic upgrade head` runs automatically in Docker) |
| `pydantic`, `pydantic-settings`, `email-validator`, `python-dotenv` | Request validation and the `.env` settings |
| `python-jose[cryptography]`, `passlib[argon2]` | JWT tokens and Argon2 password hashing |
| `redis`, `celery`, `flower` | Cache, background jobs, job monitor (used more from Phase 4) |
| `httpx` | HTTP client used by the tests |
| `structlog`, `tenacity`, `python-multipart` | Structured logging, retries, form parsing |
| `faker` | Realistic mock data for the seed script |
| `pytest`, `pytest-asyncio`, `pytest-cov` | Tests |
| `ruff` *(optional, `pip install ruff`)* | Linter, configured in `backend/ruff.toml` |

The recommendation engine and RFM scoring are plain Python - **no scikit-learn / numpy needed**.

**Flutter (Dart 3.6+) - `flutter_admin/pubspec.yaml`**

| Package | Why it is here |
|---|---|
| `flutter_riverpod` | State management and data loading |
| `dio` | HTTP client with automatic token refresh |
| `go_router` | Navigation and login redirects |
| `flutter_secure_storage` | Stores the login tokens securely |
| `intl` | Number, currency (₹) and date formatting |
| `logger` | Debug logging |
| `fl_chart` | Reserved for richer charts (current charts are plain widgets) |
| `cupertino_icons` | Icon font |
| `flutter_test`, `flutter_lints` *(dev)* | Tests and lint rules |

## 5. Setup, step by step

Unzip the project, then open **PowerShell** in the project root (the folder containing `backend/` and `flutter_admin/`).

### Path A - Docker + helper scripts (recommended, Windows)

1. **Start Docker Desktop** and wait until it is running.
2. **Allow scripts for this window only**, then set up the backend:
   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\setup_backend.ps1
   ```
   It creates `backend\.env` (with a random JWT secret), builds and starts PostgreSQL / Redis / API / worker / Flower, applies the
   database migrations, loads demo data (3 staff accounts, 500 products, 1,000 customers, ~16,000 events, 10 sample offers, 3 sample A/B tests), and calculates customer segments. First run takes a few minutes (image download).
   When it prints `Backend ready`, open http://localhost:8000/docs - you should see the Swagger page.
3. **Set up Flutter** (generates the `android/`, `windows/`, `web/` folders, installs packages, runs analysis and tests):
   ```powershell
   .\setup_flutter.ps1
   ```
4. **Run the app:**
   ```powershell
   cd flutter_admin
   flutter run -d chrome
   ```
5. **Log in** with `admin@example.com` / `ChangeMe123!` (set by `FIRST_SUPER_ADMIN_*` in `backend\.env`).

### Path B - Docker, manual commands (macOS / Linux / Windows)

```bash
# 1) backend
cd backend
cp .env.example .env                   # Windows PowerShell: Copy-Item .env.example .env
#    edit .env: set JWT_SECRET_KEY to a long random value, e.g.
#    python -c "import secrets; print(secrets.token_urlsafe(64))"
docker compose up --build -d           # starts postgres, redis, backend, worker, flower
docker compose logs -f backend         # wait for "Application startup complete", Ctrl+C to leave
docker compose exec backend python -m scripts.seed_data    # demo data + segments (add --reset to start over)

# 2) flutter
cd ../flutter_admin
flutter create . --project-name ai_personalization_admin --platforms=android,windows,web   # first time only
rm test/widget_test.dart               # Windows: del test\widget_test.dart  (template file, not used here)
flutter pub get
flutter run -d chrome
```

### Path C - No Docker (Python venv + local PostgreSQL + Redis)

```powershell
# PostgreSQL: create the role and databases (psql as the postgres user)
psql -U postgres -c "CREATE USER ai_personalization WITH PASSWORD 'ai_personalization' CREATEDB;"
psql -U postgres -c "CREATE DATABASE ai_personalization OWNER ai_personalization;"
# Redis must be running on localhost:6379

cd backend
py -3.12 -m venv .venv                 # macOS/Linux: python3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1           # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
Copy-Item .env.example .env
# point .env at localhost instead of the Docker host names:
(Get-Content .env) -replace '@postgres:','@localhost:' -replace 'redis://redis:','redis://localhost:' | Set-Content .env

alembic upgrade head                   # create tables
python -m scripts.seed_data            # demo data
uvicorn app.main:app --reload --port 8000
# optional worker (Windows needs --pool=solo): celery -A app.workers.celery_app worker --loglevel=info --pool=solo
```
Then run the Flutter steps from Path B.

### Starting and stopping later

| Task | Command (in `backend/`) |
|---|---|
| Start everything | `docker compose up -d` |
| Stop (keep data) | `docker compose down` |
| Stop and **delete all data** | `docker compose down -v` |
| Pick up code changes | `docker compose up --build -d` |
| See API logs | `docker compose logs -f backend` |
| Rebuild demo data | `docker compose exec backend python -m scripts.seed_data --reset` |

### Create users and service accounts

There is no sign-up screen. The seed script creates demo accounts; after that, **admins manage people in the app: sidebar → Users → New user**
(name, email, role, password; edit, disable or reset a password later). From the command line you can do the same - handy for the very
first account or for scripts:

```bash
cd backend
docker compose exec backend python -m scripts.create_user --email shop@yourstore.com --password "a-long-password" --role ADMIN --name "Store backend"
docker compose exec backend python -m scripts.create_user --email maya@yourstore.com --password "another-password" --role MARKETING_MANAGER
# change a password or role later:
docker compose exec backend python -m scripts.create_user --email maya@yourstore.com --password "new-password" --role ADMIN --update
```
Path C (no Docker): run `python -m scripts.create_user ...` from `backend/` with the venv active.

**Demo accounts** (created by the seed script; all use the password from `FIRST_SUPER_ADMIN_PASSWORD`, default `ChangeMe123!`):
`admin@example.com` (Super Admin) · `marketing@example.com` (Marketing Manager) · `viewer@example.com` (Viewer). Log in as each to see how the
sidebar and permissions change. **Delete or re-password them before real use.**

| Role | Can do |
|---|---|
| `SUPER_ADMIN` | Everything, including creating / changing other Super Admins |
| `ADMIN` | Everything except managing Super Admins: users, system page, push products, Recompute, Rebuild model, offers, checkout API |
| `MARKETING_MANAGER` | Manage offers and use the checkout API (validate / redeem); read everything else |
| `DATA_ANALYST`, `VIEWER` | Read-only dashboards (no Users / System pages) |

Safety rules: you cannot change your own role or disable yourself, the last Super Admin cannot be removed, and disabling a user or changing
their password signs them out immediately.

> **Upgrading from an earlier phase?** Unzip the new version over the old one, run `docker compose up --build -d` inside `backend`
> (migrations run automatically), then `docker compose exec backend python -m scripts.seed_data --reset` once so the demo data has
> realistic shopping patterns, customer segments, sample offers and the demo staff accounts. Your admin login is kept. Then `flutter pub get` and run the app again.

## 6. Run the Flutter app on every platform

All commands run inside `flutter_admin/`. The app talks to `http://localhost:8000/api/v1` unless you change `API_BASE_URL`.

| Where | Command | Notes |
|---|---|---|
| **Chrome** | `flutter run -d chrome` | Easiest. Any random port works (CORS allows `localhost:*`) |
| **Windows desktop** | `flutter run -d windows` | Needs Visual Studio C++ (see section 3) |
| **Android phone (USB)** | `adb reverse tcp:8000 tcp:8000` then `flutter run -d <device-id>` | Enable *USB debugging*. No IP address or firewall changes needed |
| **Android emulator** | `flutter run -d <emulator-id> --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1` | `10.0.2.2` is the emulator's name for your PC |
| **Phone over Wi-Fi** | `flutter run --dart-define=API_BASE_URL=http://192.168.1.23:8000/api/v1` | Use your PC's IP; allow port 8000 in Windows Firewall |
| **Release build** | `flutter build web` / `windows` / `apk` | Use an `https://` API URL for real deployments |

List your devices with `flutter devices`.

## 7. Using the app

| URL | What it is |
|---|---|
| http://localhost:8000/docs | Swagger UI - try every API call (click **Authorize** and paste a token from `/auth/login`) |
| http://localhost:8000/api/v1/ready | Shows whether PostgreSQL and Redis are reachable |
| http://localhost:5555 | Flower - Celery job monitor |

| Screen | What to try |
|---|---|
| **Dashboard** | KPIs (customers, products, recommendations served + CTR), 14-day activity chart, events by type, top categories, customer segment chart. Refresh icon reloads |
| **Experiments** | KPIs and a card per A/B test. **New experiment** (key, hypothesis, what is tested, primary metric, traffic %, 2-5 variants). Open one: the **verdict** banner (collecting / winner / control better / no clear difference), per-variant results with lift and p-value, Start / Pause / Resume / Complete (pick the winner), and a checker that shows which variant a customer would get |
| **Analytics** | Pick 7 / 14 / 30 / 90 days. Seven KPIs with the change versus the previous period, a daily chart you can switch (revenue, orders, events, active / new customers), the customer funnel, platforms, top products and categories, recommendation and offer performance |
| **Integrations** | A setup checklist with a progress bar (catalog synced? events arriving? purchases tracked? ids matching?), data-health numbers, accounts, and copy-paste `curl` examples for connecting your shop |
| **Users** *(admins)* | Everyone who can sign in. **New user**, click a row to edit the name / role, reset the password or disable the account |
| **System** *(admins)* | App version and uptime, database and Redis health, table sizes, background jobs, active settings, and all alerts |
| **Top bar** | **Search** customers, products and offers; the **bell** lists things that need attention (with a badge); the moon / sun switches dark mode (remembered). On phones these are in the app bar |
| **Offers** | KPIs (active, impressions, clicks, redemptions, discount given). **New offer** opens the form (type, discount, caps, budget, dates, target segments / categories, priority). Each card has a menu: Edit, Activate / Resume, Pause, End. **Try it** shows which offers a customer would get and why |
| **Customers** | Filter by segment, search an ID (`USER_10005`), sort by spend / RFM. Click a customer: segment + suggested action, RFM bars, metrics, **recommended products**, **offers they qualify for**, behaviour timeline |
| **Segments** | 5x5 RFM heat-map and a card per segment (size, revenue share, advice). **View customers** jumps to the filtered list. **Recompute** refreshes profiles |
| **Products** | Search / filter / sort. Click a product: *Similar products* and *Frequently bought together* with the reason for each |
| **Recommendations** | Engine status (model size, usage per algorithm), **Rebuild model**, and a playground: pick a mode, enter `USER_10005` or `PROD_1010`, see results |

Roles: `SUPER_ADMIN` / `ADMIN` can write everything (push products, Recompute, Rebuild model, offers); `MARKETING_MANAGER` manages offers; other roles can read.

## 8. Configuration reference

**Backend - `backend/.env`** (copy of `.env.example`; Docker reads it automatically; restart the backend after editing)

| Variable | Default | Meaning |
|---|---|---|
| `JWT_SECRET_KEY` | *(must set)* | Long random secret that signs login tokens. **Change it** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | 30 / 7 | Token lifetimes |
| `DATABASE_URL`, `DATABASE_URL_SYNC` | host `postgres` | Use host `localhost` when running without Docker |
| `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | host `redis` | Same - `localhost` without Docker |
| `CORS_ORIGINS` | localhost list | Extra allowed web origins (comma-separated). Any `localhost:<port>` is allowed automatically |
| `RECO_LOOKBACK_DAYS` / `RECO_HALF_LIFE_DAYS` | 90 / 30 | History window for recommendations; older events count less |
| `RECO_SNAPSHOT_TTL_SECONDS` | 300 | How long the model is cached before it is rebuilt |
| `RECO_EXCLUDE_OUT_OF_STOCK` | true | Never recommend products that are out of stock |
| `RECO_FBT_MIN_SUPPORT` | 2 | Orders needed before two products count as "bought together" |
| `CUSTOMER_LOOKBACK_DAYS` | 365 | History used for RFM |
| `CUSTOMER_ACTIVE_DAYS` | 30 | "Recent" window (new customers, prospects) |
| `CUSTOMER_PROFILE_REFRESH_MINUTES` | 60 | Automatic segment refresh; `0` = only on **Recompute** |
| `FIRST_SUPER_ADMIN_EMAIL` / `_PASSWORD` | admin@example.com / ChangeMe123! | Admin created by the seed script. Change before seeding |

Offers need no extra settings. **Flutter:** `--dart-define=API_BASE_URL=http://host:8000/api/v1` (default `http://localhost:8000/api/v1`).

## 9. Connect your own shop data

The demo data is random; to use real data your shop calls the API. Log in once with an admin / service account (see *Create users and service accounts* above) to get a token:

```powershell
$login = Invoke-RestMethod -Method Post http://localhost:8000/api/v1/auth/login -ContentType 'application/json' `
  -Body '{"email":"admin@example.com","password":"ChangeMe123!"}'
$h = @{ Authorization = "Bearer $($login.data.access_token)" }

# 1. products (needs the token)
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/products/bulk -Headers $h -ContentType 'application/json' -Body `
 '{"products":[{"product_id":"SKU-1","name":"Acme Laptop","category":"Laptops","brand":"Acme","price":59999,"in_stock":true}]}'

# 2. events (no token). Send the SAME session_id for everything bought together; quantity/amount are optional
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/events -ContentType 'application/json' -Body `
 '{"event_type":"PURCHASE","external_user_id":"U1","product_id":"SKU-1","session_id":"order-77","timestamp":"2026-10-08T10:00:00Z","metadata":{"quantity":1}}'

# 3. recommendations (no token) and customer segments (token)
Invoke-RestMethod http://localhost:8000/api/v1/recommendations/user/U1
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/customers/recompute -Headers $h
```

**Offers: the full shop flow.** Create offers in the **Offers** screen (or `POST /offers`), activate them, then your shop does:

```powershell
# a) product page / cart: which offers can this customer use? (no token) - show them, then report what was displayed
Invoke-RestMethod "http://localhost:8000/api/v1/offers/user/U1?cart_value=2500&category=Laptops"
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/offers/track -ContentType 'application/json' `
  -Body '{"code":"VIP15","external_user_id":"U1","action":"impression"}'      # later: "action":"click"

# b) checkout, customer typed a coupon (token needed): is it valid for this customer and cart?
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/offers/validate -Headers $h -ContentType 'application/json' `
  -Body '{"code":"VIP15","external_user_id":"U1","order_value":2500,"categories":["Laptops"]}'
#    -> valid, discount_amount, final_value  (or valid=false with reason_code + reason to show the customer)

# c) the order was placed (token needed): redeem once. Same order_id again is safe - it returns duplicate=true
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/offers/redeem -Headers $h -ContentType 'application/json' `
  -Body '{"code":"VIP15","external_user_id":"U1","order_id":"ORD-1001","order_value":2500,"categories":["Laptops"]}'
```

| Call | Login? | Who |
|---|---|---|
| `GET /offers/user/{id}`, `POST /offers/track` | no | storefront |
| `POST /offers/validate`, `POST /offers/redeem` | yes (`ADMIN`, `SUPER_ADMIN`, `MARKETING_MANAGER`) | your shop's backend, never the browser |
| `GET /offers`, `/offers/stats` | yes (any role) | dashboard |
| create / edit / status | yes (`ADMIN`, `SUPER_ADMIN`, `MARKETING_MANAGER`) | marketing |

Segment-targeted offers reach a customer once they are scored (hourly or **Recompute**). One discount per order - the shop decides which valid code to apply.

Event types: `PRODUCT_VIEW, PRODUCT_SEARCH, CATEGORY_VIEW, WISHLIST_ADD, WISHLIST_REMOVE, ADD_TO_CART, REMOVE_FROM_CART, CHECKOUT_STARTED,
PURCHASE, PURCHASE_CANCELLED, RETURN, PRODUCT_REVIEW, OFFER_VIEW, OFFER_CLICK, OFFER_REDEEM, RECOMMENDATION_VIEW, RECOMMENDATION_CLICK`.
Timestamps **must include a timezone** (`Z` or `+05:30`). Full details: [`docs/API.md`](docs/API.md).

How it works: **recommendations** blend popularity, content similarity, "customers who liked this also liked", and purchase baskets,
never showing out-of-stock or already-bought items. **Segments** score each buyer 1-5 on how *recently* they bought, how *often*, and
how *much* they spent, then apply rules (e.g. R≥4, F≥4, M≥4 = Champions). See `docs/ARCHITECTURE.md`.

### A/B testing guide (Experiments)

An experiment shows **different things to different customers** and measures who buys more. Two surfaces can be tested:

| Test | Variants differ in | Example |
|---|---|---|
| **Recommendations** | the strategy behind `GET /recommendations/user/{id}`: *hybrid* (default), *content-based*, *collaborative*, *popular* | "Does the hybrid engine beat plain popular items?" |
| **Offers** | which offers `GET /offers/user/{id}` may show: all, only chosen codes, or **none** (holdout) | "Does COMEBACK20 bring lapsed customers back, or would they come anyway?" |

**Run one in six steps**
1. Experiments → **New experiment**. Give it a key and name, write a hypothesis, choose *what is tested* and the **primary metric**
   (purchase conversion, click rate or revenue per customer - pick ONE before you start).
2. Set **traffic** (the share of customers that take part; 100% = everyone) and the variants. The **first variant is the control** (today's behaviour).
   Weights split the traffic (1 and 1 = 50 / 50).
3. **Start** it. Nothing else to integrate: your site already calls the serving endpoints, and the first time a customer is served they are assigned
   to a variant (the response includes `"experiment": {"key": ..., "variant": ...}`). Use *Check a customer* on the detail page to see who gets what.
4. Wait for data. The banner says **Collecting data** until every variant has 30 exposed customers, then **No clear difference yet** (it tells you how
   many customers a 10% lift would need) or **We have a winner / The control is better**. A result is called significant when p < 0.05.
5. **Complete** it and pick the winner (the data's suggestion is marked). Completed tests stop assigning customers - then ship the winning setting
   (e.g. make that strategy your default, or keep that offer running) yourself.
6. Start the next idea.

**Good practice:** decide the primary metric before you start; do not stop the moment a number looks good (wait for the sample size);
run for at least one full week so weekdays and weekends are both covered; change one thing at a time. Only one experiment can run per surface
(recommendations / offers) at a time, running experiments cannot be edited (that would corrupt the results), and outcomes are only counted after a
customer was first shown a variant. The demo data includes a finished win-back test with a winner and a running recommendations test.

## 10. Tests and code checks

```bash
# Backend (Docker)             -> 246 tests
docker compose exec backend pytest -v
# Backend (venv, Path C)
pytest -q
# Optional linter
pip install ruff && ruff check app scripts tests

# Flutter (inside flutter_admin/)   -> 36 tests
flutter analyze
flutter test
```
Backend tests always use a **separate `<database>_test` database** (created automatically) - your real data is never touched.

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| `docker: error during connect` / "cannot connect to the Docker daemon" | Docker Desktop is not running. Start it, wait for "running", retry |
| `port is already allocated` (5432 / 6379 / 8000 / 5555) | Another program uses it. Stop it (e.g. a local PostgreSQL), or change the left side of the port mapping in `docker-compose.yml` |
| `running scripts is disabled` | Run `Set-ExecutionPolicy -Scope Process Bypass` in that PowerShell window first |
| `docker compose` not found | Update Docker Desktop (needs Compose v2). Old installs use `docker-compose` |
| Backend exits right after start | `docker compose logs backend`. Usually a missing/invalid `.env` (e.g. `JWT_SECRET_KEY` not set) |
| Login fails / "Network error" in the app | Check http://localhost:8000/api/v1/health opens. Android phone: run `adb reverse tcp:8000 tcp:8000`; emulator: use `10.0.2.2` (section 6) |
| Browser console shows a **CORS** error | The API must be reachable at `localhost`/`127.0.0.1`. For another host add it to `CORS_ORIGINS` and restart the backend |
| Dashboard shows `—`, empty lists, "No customer profiles yet" | No data yet: run the seed command, or send events and press **Recompute** |
| Customers show "Not scored" | Press **Recompute** (Segments or Customers page). It also runs automatically every hour |
| **Recompute / Rebuild model** says forbidden | Only `ADMIN` / `SUPER_ADMIN` accounts can do this. Log in as the seeded admin |
| Recompute says "already running" | Another recompute is in progress - wait a few seconds and retry |
| Cannot start an experiment: "already running" (`EXPERIMENT_KIND_BUSY`) | Only one test per surface can run. Pause or complete the other one first |
| Cannot start an offers experiment: unknown offer code | Create the offer first (codes are case-insensitive), or fix the code in the draft |
| Experiment shows 0 exposed customers | Your site must call `GET /recommendations/user/{id}` (or `/offers/user/{id}`) for real customers; check traffic % and that the test is *Running* |
| "Collecting data" for a long time | Each variant needs 30+ exposed customers before a verdict. Raise the traffic %, or wait |
| "No clear difference yet" | Not enough customers to detect a small lift (the banner shows how many are needed) or there really is no difference - both are valid results |
| Edit button is missing on an experiment | Only drafts can be edited; changing a live test would invalidate its results. Complete it and create a new one |
| Users / System pages are missing from the sidebar | They are for `ADMIN` / `SUPER_ADMIN` only. Log in with an admin account |
| "Only a Super Admin can manage Super Admin accounts" | Log in as a Super Admin (e.g. `admin@example.com`) to create or change Super Admins |
| "You cannot change your own role or deactivate your own account" | By design - ask another admin to do it |
| Analytics charts are empty | The period has no events. Send events (or `seed_data --reset`) and pick a longer period |
| Integrations shows `todo` / `warning` items | Each item says what to do. Unknown product ids = push those products to the catalog; purchases without `session_id` = send one id per order |
| Bell shows a red number | Open it: each alert links to the page that fixes it (e.g. Recompute segments, send events) |
| Dark mode does not stick | The choice is saved in the browser / device secure storage; clearing site data resets it |
| **Offers**: `valid: false` at checkout | Read `reason_code`: `NOT_ELIGIBLE` = customer's segment is not targeted (or not scored yet - press Recompute), `CATEGORY_NOT_MATCHED` = send `categories` in the request, `MIN_ORDER_NOT_MET`, `LIMIT_REACHED`, `CUSTOMER_LIMIT_REACHED`, `EXPIRED`, `NOT_ACTIVE` (draft / paused / ended) |
| Offer does not show for a customer in the storefront call | It must be **Active** (not draft/paused), inside its dates, targeted at that customer's segment, with budget left; check with the **Try it** box on the Offers page |
| "Create offer" says the code already exists | Codes are unique and not case-sensitive (`vip15` = `VIP15`) |
| `403` on validate / redeem / create offer | The account's role must be `ADMIN`, `SUPER_ADMIN` or `MARKETING_MANAGER` - create one with `scripts.create_user` |
| An ended offer cannot be edited or restarted | By design - duplicate it as a new offer with a new code |
| Recommendations look random | The data is random demo data. `seed_data --reset` creates patterned data; real events make it meaningful |
| `flutter test` fails mentioning `MyApp` | Delete `flutter_admin/test/widget_test.dart` (template file created by `flutter create`) |
| Windows build error `atlstr.h not found` | Visual Studio Installer → Modify → add **C++ ATL for latest build tools** |
| Android build: cleartext / network blocked | `setup_flutter.ps1` patches `AndroidManifest.xml` for development; for production use HTTPS |
| `flutter pub get` version conflicts | Update Flutter (`flutter upgrade`); the project needs Flutter 3.27+ |
| Tables missing / "relation does not exist" | `docker compose exec backend alembic upgrade head` (it normally runs on start) |
| Want a completely fresh start | `docker compose down -v`, then `.\setup_backend.ps1` again |
| `alembic` / `pytest` "No module named app" (Path C) | Run them from inside the `backend/` folder with the venv activated |

## 12. Project layout

```
backend/
  app/
    main.py                FastAPI app, CORS, error format, routers, background refresh
    core/                  settings, security, logging, health, response helpers
    database/              async engine, models, Alembic migrations (5 revisions)
    auth/                  login / refresh / logout / roles
    events/                idempotent event ingestion
    products/              catalog sync + listing
    recommendations/       engine.py (algorithms), service.py (data + cache), router.py
    customers/             intelligence.py (RFM + segments), service.py, router.py, scheduler.py
    segments/              segment definitions + API
    analytics/ integrations/ system/ users/ search/   Phase 5 backend modules
    experiments/           engine.py (assignment + statistics), service.py, router.py
    offers/                engine.py (eligibility, discount, ranking), service.py, router.py
    analytics/             dashboard numbers
  scripts/seed_data.py     demo data (--reset to rebuild)
  scripts/create_user.py   create admin / marketing / service-account users
  tests/                   246 tests
  docker-compose.yml  Dockerfile  requirements.txt  .env.example  ruff.toml  alembic.ini
flutter_admin/
  lib/core/                API client, routing, theme, shared widgets, formatters
  lib/features/            auth, dashboard, customers, segments, products, recommendations, offers,
                           analytics, integrations, system_health, users, search, experiments
  test/                    36 tests
docs/                      API.md  ARCHITECTURE.md  ROADMAP.md
setup_backend.ps1  setup_flutter.ps1
```

## 12b. Welfog (existing shop) integration

Syncing an existing shop's MySQL/Postgres data, the tracking SQL and the API contract are described in
`docs/WELFOG_INTEGRATION.md`. Run `python -m scripts.welfog_sync --dry-run` first.

## 13. Security and going to production

- Change `JWT_SECRET_KEY` and `FIRST_SUPER_ADMIN_PASSWORD` before sharing the server; never commit `.env`.
- `/events`, `/recommendations/*` (serving) are open like a storefront API - keep them on a private network or behind your gateway until API-key
  auth is added. Product writes, customer data, user management, system status, offer management and the checkout calls (`validate` / `redeem`) require a login - call those from your server, never from the browser.
- Use HTTPS in front of the API and remove the Android cleartext setting for release builds.
- Back up the `postgres_data` Docker volume; `docker compose down -v` deletes it.

Licence / ownership: see your project agreement.
