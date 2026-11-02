# Development Roadmap

Each phase is built, tested, and confirmed working before the next begins.

## ✅ Phase 1 — Foundation
- FastAPI + PostgreSQL + Redis + Docker Compose
- JWT auth (login/refresh/logout/me) + RBAC (5 roles)
- Event ingestion (single + batch) with idempotency
- Health/readiness checks
- Mock data generator (1 admin, 500 products, 1,000 customers, 10,500+ events)
- Flutter: login screen, dashboard shell (responsive sidebar/drawer), auth-aware routing, live system-health widget

## ✅ Phase 2 — Recommendation MVP
- Popularity (time-decayed), content-based, item-item collaborative filtering, frequently-bought-together, personalised hybrid
- `GET /recommendations/popular`, `/user/{id}`, `/home/{id}`, `/similar/{product_id}`, `/frequently-bought/{product_id}`
- Impression/click tracking (`POST /recommendations/track`), CTR, usage per algorithm
- Product catalog API (single + bulk upsert, search/filter/sort/paginate), `GET /analytics/overview`
- Seed data with real shopping patterns (`python -m scripts.seed_data --reset`)
- Flutter: live dashboard (KPIs + charts), Products screen with per-product recommendations, Recommendation Engine screen (status + playground)
- Known limits (addressed in Phase 7/8): model lives in one process's memory and is rebuilt from SQL aggregates (fine for hundreds of thousands of events);
  no background training job, no image-based similarity

## ✅ Phase 3 — Customer Intelligence
- Customer profile aggregation (orders, spend, returns, favourite category/brand, activity) and behaviour timeline
- RFM scoring (Recency/Monetary percentile ranks, Frequency bins) and 12 rule-based segments with suggested actions
- `GET /customers`, `/customers/{id}`, `/customers/{id}/timeline`, `/customers/stats`, `POST /customers/recompute`, `GET /segments`
- Automatic hourly refresh (advisory-locked, safe with several workers) plus manual Recompute
- Flutter: Customers list + customer detail (RFM bars, recommendations, timeline), Segments page (RFM grid + cards), dashboard segment chart

## ✅ Phase 4 — Offer Engine
- Offer CRUD with a lifecycle (draft → active ⇄ paused → ended; scheduled / expired are derived from the dates)
- Targeting by customer segment (RFM) and category; guardrails: max discount, min order value, total budget, uses per customer
- Personalised ranking (`GET /offers/user/{id}`): segment fit, category interest, value, priority, urgency, observed conversion
- Checkout API: `POST /offers/validate` and `POST /offers/redeem` (idempotent by order id, race-safe budget enforcement)
- Impression / click tracking (`POST /offers/track`), per-offer performance (CTR, redemptions, discount given, revenue)
- `python -m scripts.create_user` to create service accounts and marketing users
- Flutter: Offers screen (create / edit / activate / pause / end, KPIs, playground), offers on the customer page and dashboard
- Known limits: one discount per order (no stacking), no BOGO / product-level discounts yet, no A/B testing of offers (Phase 6)

## ✅ Phase 5 — Flutter Dashboard (full)
- Every sidebar screen except Experiments: Dashboard, Customers, Segments, Products, Recommendations, Offers, **Analytics, Integrations, Users, System**
- **Analytics:** 7/14/30/90-day report compared with the previous period (revenue, orders, AOV, active/new customers, conversion, events), daily charts, customer funnel, top products and categories, platforms, recommendation and offer performance (`GET /analytics/report`)
- **Integrations:** setup checklist with a progress score, data-quality checks (unknown product ids, purchases without session id), copy-paste API examples (`GET /integrations/status`)
- **System (admins):** versions, uptime, database and Redis health, table sizes, background jobs, active settings (`GET /system/status`)
- **Users (admins):** list, create, edit, disable, reset password from the UI with role rules (`/users`); sessions end when a user is disabled or the password changes
- **Top bar:** global search (customers, products, offers), notification bell with alerts (stale events, stale segments, offers ending / over budget, low stock), dark-mode toggle that is remembered; the same actions are in the mobile app bar
- Role-aware sidebar (Users and System are for admins only)

## ✅ Phase 6 — A/B Testing (this release)
- Experiments on two surfaces: **recommendations** (strategy per variant: hybrid / content / collaborative / popular) and **offers** (which offers a variant may see, including a no-offer holdout)
- Sticky, stateless customer assignment (hashing) with traffic allocation and variant weights; an exposure is stored the first time a customer is served, outcomes are counted only after it
- Lifecycle draft → running ⇄ paused → completed (with an optional winner); one running experiment per surface; only drafts are editable
- Statistics: purchase conversion and click rate (two-proportion z-test), revenue per customer (Welch t-test), 95% confidence intervals, p-values, lift, minimum sample size and a plain-language verdict (collecting / winner / control better / inconclusive) plus the sample size needed for a 10% lift
- API: `/experiments` (CRUD, status, results, assignment preview, stats); serving responses carry an `experiment` field; alerts for idle experiments and decided results
- Flutter: Experiments list, create / edit form with a variants editor, detail page with verdict, per-variant results, lifecycle actions and a "which variant would customer X get?" checker
- Known limits: one live test per surface, no multi-armed bandits, p-values are not corrected for many variants (compare against the control only)

## ✅ Phase 7 — Advanced ML (this release)
- **Purchase Probability Model** – probability a customer buys in the next 30 days (RFM + engagement signals → logistic-sigmoid scoring)
- **Churn Risk Model** – probability a customer has churned or is at imminent churn risk (recency, RFM, activity, returns)
- **Offer Response Prediction** – which offer type (discount / loyalty_reward / win_back / none) each customer is most likely to respond to (segment affinity + behaviour modifiers)
- **Model versioning** – ModelRegistry tracks version, training timestamp, customer count, average score, high-risk count and an estimated AUC for each model
- **API**: `GET /ml/models` · `POST /ml/rebuild` · `GET /ml/customers/{id}` (all three) · `/purchase` · `/churn` · `/offer` · `GET /ml/top/churn` · `GET /ml/top/purchase` · `GET /ml/distribution/{model}`
- **Flutter**: ML Insights screen (sidebar → ML Insights) with model status cards, Churn Risk / Purchase Probability leaderboards, animated score distribution histogram, and a Playground tab to look up all three predictions for any customer. ML predictions panel added to customer detail pages.
- All models are pure Python — no scikit-learn, no numpy; they run in the same process as the API
- Scores cached in Redis for 6 hours; one `POST /ml/rebuild` scores all customers in a single batch pass
- Known limits: models use hand-tuned logistic scoring, not learned from labelled outcomes; no online updates between rebuilds

## ✅ Phase 8 — Production Hardening (completed)
- **Security hardening**: OWASP-recommended security headers middleware (`X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `HSTS`), request payload size limiter (`413 PAYLOAD_TOO_LARGE`), anti-bruteforce Redis rate limiter on `/auth/login`, and production secret validation on startup
- **Observability & Metrics**: Prometheus metrics collection & exporter (`/metrics` and `/api/v1/metrics`), distributed request tracing (`X-Request-ID`, `X-Response-Time`), and deep readiness probes (`/api/v1/ready`) measuring DB & Redis latencies
- **Performance & Load testing**: Async benchmark tool (`scripts/load_test.py`) with support for concurrent recommendations, event ingestion, and offer evaluations with latency percentile breakdowns (p50, p95, p99)
- **Production Deployment Assets**: Production Docker Compose (`docker-compose.prod.yml`), Nginx reverse proxy configuration (`deploy/nginx/nginx.conf`), hardened Redis configuration (`deploy/redis/redis.conf`), and automated database backup scripts (`scripts/backup_db.ps1`, `scripts/backup_db.sh`)
- **Documentation**: Comprehensive production deployment guide ([`docs/DEPLOYMENT.md`](DEPLOYMENT.md))
- **Test coverage**: Full unit & integration test coverage (`tests/test_production_hardening.py`) passing with 100% success rate
