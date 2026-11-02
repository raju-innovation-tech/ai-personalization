# Production Deployment & Hardening Guide (Phase 8)

This guide documents the procedures for deploying, securing, monitoring, and operating the **AI Personalization & Offer Engine** in a high-availability production environment.

---

## 1. Production Architecture

```
Internet / Storefront
        │
    HTTPS (443)
        ▼
┌───────────────────────────────────────────────┐
│              Nginx Reverse Proxy              │
│  - SSL/TLS termination (TLS 1.2 / 1.3)        │
│  - HTTP/2 + Gzip / Brotli compression         │
│  - Edge rate limiting (DDoS & Brute Force)    │
│  - Static security headers                    │
└───────────────────────┬───────────────────────┘
                        │
                        ▼ (internal Docker network)
┌───────────────────────────────────────────────┐
│        FastAPI Application Cluster            │
│  - Uvicorn multi-worker process (4+ workers)  │
│  - Security headers & payload size guardrails │
│  - Distributed request tracing (X-Request-ID) │
│  - Prometheus metrics exporter (/metrics)     │
└──────┬────────────────┬───────────────┬───────┘
       │                │               │
       ▼                ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌─────────────┐
│  PostgreSQL  │ │    Redis     │ │   Celery    │
│  16 (Primary)│ │  7 (Cache /  │ │   Workers   │
│  - Pool ping │ │   Broker)    │ │ - Profiling │
│  - Auto AOF  │ │  - AOF sync  │ │ - Recs sync │
└──────────────┘ └──────────────┘ └─────────────┘
```

---

## 2. Production Security Checklist

- [x] **No Default Secrets**: Set strong secrets for `JWT_SECRET_KEY` and `POSTGRES_PASSWORD`. The application automatically halts at startup if default development keys are detected in `APP_ENV=production`.
- [x] **Security Response Headers**:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
- [x] **DDoS & Payload Size Limits**: Payloads over 10MB are rejected with `413 PAYLOAD_TOO_LARGE` before consuming memory.
- [x] **Anti-Bruteforce Rate Limiting**: `/api/v1/auth/login` is limited to 15 requests per minute per IP via Redis.
- [x] **Database Pool Recycling**: Connections are recycled every 30 minutes (`DB_POOL_RECYCLE_SECONDS=1800`) with active pre-ping to prevent broken pipe disconnects.

---

## 3. Production Deployment (Docker Compose)

### 3.1. Prepare Production Environment Variables
Create `.env.production` inside `backend/`:
```bash
APP_NAME="AI Personalization Engine"
APP_ENV=production
DEBUG=false
API_V1_PREFIX=/api/v1

# Security: Generate a 64-character random key
# python -c "import secrets; print(secrets.token_urlsafe(64))"
JWT_SECRET_KEY=PUT_YOUR_STRONG_64_CHAR_SECRET_HERE

POSTGRES_USER=aip_admin
POSTGRES_PASSWORD=STRONG_DB_PASSWORD_HERE
POSTGRES_DB=ai_personalization

DATABASE_URL=postgresql+asyncpg://aip_admin:STRONG_DB_PASSWORD_HERE@postgres:5432/ai_personalization
DATABASE_URL_SYNC=postgresql+psycopg2://aip_admin:STRONG_DB_PASSWORD_HERE@postgres:5432/ai_personalization

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

CORS_ORIGINS=https://admin.yourstore.com,https://yourstore.com
```

### 3.2. Launch Production Services
```bash
cd backend
docker compose -f docker-compose.prod.yml up --build -d
```

Verify service health:
```bash
docker compose -f docker-compose.prod.yml ps
curl -i http://localhost/api/v1/health
```

---

## 4. Observability & Monitoring

### 4.1. Prometheus Metrics
The API exposes Prometheus-compatible metrics on `/metrics` and `/api/v1/metrics`:
- `http_requests_total{method, path, status}`
- `http_request_duration_seconds_count` & `http_request_duration_seconds_sum`
- `app_info{version, env}`

Prometheus scrape configuration (`prometheus.yml`):
```yaml
scrape_configs:
  - job_name: 'ai-personalization-engine'
    scrape_interval: 15s
    metrics_path: '/api/v1/metrics'
    static_configs:
      - targets: ['backend:8000']
```

### 4.2. Deep Readiness Probe (`/api/v1/ready`)
Designed for Kubernetes and load balancers:
- Queries PostgreSQL (`SELECT 1`) and measures latency.
- Pings Redis and measures latency.
- Returns `HTTP 200` with `status: ready` if healthy; returns `HTTP 503` if any critical dependency is offline.

---

## 5. Load Testing & Benchmarks

Run the built-in asynchronous performance test:
```powershell
# From the backend directory:
python -m scripts.load_test --scenario mixed --concurrency 30 --requests 1000
```
Scenarios available:
- `mixed`: 70% recommendations, 20% event ingestion, 10% offer evaluation.
- `recommendations`: Pure recommendation retrieval under high concurrency.
- `events`: Ingestion throughput test.
- `offers`: Coupon redemption & validation under load.

Target Performance:
- **P95 Latency**: < 40ms on standard recommendation endpoints.
- **Error Rate**: 0.00% under normal concurrency limits.

---

## 6. Backup & Disaster Recovery

### Automated PostgreSQL Backup
- **Windows**: Run `.\backend\scripts\backup_db.ps1`
- **Linux**: Run `./backend/scripts/backup_db.sh`

Both scripts automatically:
1. Stream `pg_dump -F c` from the running PostgreSQL container.
2. Store timestamped `.dump` files in the `backups/` directory.
3. Automatically delete backup snapshots older than 14 days.

### Restore Procedure
```bash
docker compose exec -T postgres pg_restore -U aip_admin -d ai_personalization -c -v "/path/to/backup.dump"
```
