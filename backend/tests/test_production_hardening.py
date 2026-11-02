"""
Tests for Phase 8 — Production Hardening & Observability.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.metrics import metrics_collector
from app.core.rate_limit import InMemoryFallbackLimiter, RateLimiter
from app.main import app, lifespan


@pytest.mark.asyncio
async def test_security_headers_present():
    """Verify that OWASP-recommended security headers are added to every HTTP response."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/health")
        assert res.status_code == 200
        assert res.headers.get("x-content-type-options") == "nosniff"
        assert res.headers.get("x-frame-options") == "DENY"
        assert res.headers.get("x-xss-protection") == "1; mode=block"
        assert res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert "x-request-id" in res.headers
        assert "x-response-time" in res.headers


@pytest.mark.asyncio
async def test_payload_too_large_rejection():
    """Verify that oversized requests are rejected with HTTP 413."""
    oversized_headers = {"Content-Length": str(settings.MAX_CONTENT_LENGTH_BYTES + 1000)}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/events", headers=oversized_headers, json={})
        assert res.status_code == 413
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint():
    """Verify that Prometheus metrics scrape endpoint exports valid metrics."""
    # Record a test metric
    metrics_collector.inc_counter("events_ingested_total", 5.0, {"event_type": "PURCHASE", "status": "accepted"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/metrics")
        assert res.status_code == 200
        assert "text/plain" in res.headers.get("content-type", "")
        text = res.text
        assert "# HELP http_requests_total" in text
        assert "# TYPE http_requests_total counter" in text
        assert "app_info" in text

        # Also test API v1 prefix route
        res_v1 = await client.get("/api/v1/metrics")
        assert res_v1.status_code == 200


@pytest.mark.asyncio
async def test_deep_readiness_probe():
    """Verify that /api/v1/ready returns status, checks, and latencies."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/ready")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "checks" in data
        assert "latencies" in data
        assert data["checks"]["database"] == "ok"
        assert "database_ms" in data["latencies"]


@pytest.mark.asyncio
async def test_in_memory_rate_limiter():
    """Verify in-memory fallback rate limiter blocks requests exceeding the threshold."""
    limiter = InMemoryFallbackLimiter()
    key = "test-client-ip"
    limit = 3
    window = 60

    # 3 allowed requests
    for _ in range(limit):
        allowed, retry_after = limiter.is_allowed(key, limit, window)
        assert allowed is True
        assert retry_after == 0

    # 4th request must be blocked
    allowed, retry_after = limiter.is_allowed(key, limit, window)
    assert allowed is False
    assert retry_after > 0


@pytest.mark.asyncio
async def test_production_secret_guard():
    """Verify that insecure JWT keys are rejected on startup when in production mode."""
    original_env = settings.APP_ENV
    original_key = settings.JWT_SECRET_KEY
    try:
        settings.APP_ENV = "production"
        settings.JWT_SECRET_KEY = "test-secret-key-for-pytest-only"

        with pytest.raises(RuntimeError, match="CRITICAL: Insecure or short JWT_SECRET_KEY"):
            async with lifespan(app):
                pass
    finally:
        settings.APP_ENV = original_env
        settings.JWT_SECRET_KEY = original_key
