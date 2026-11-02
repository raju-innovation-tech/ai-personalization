import time
from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.responses import success_response
from app.database.database import get_db

router = APIRouter(tags=["Health"])

_redis_client: Redis | None = None
_start_time = time.time()


def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


@router.get("/health")
async def health():
    """Liveness probe — verifies the web worker process is up and answering."""
    uptime_seconds = int(time.time() - _start_time)
    return success_response({
        "status": "ok",
        "service": settings.APP_NAME,
        "env": settings.APP_ENV,
        "uptime_seconds": uptime_seconds,
    })


@router.get("/ready")
async def ready(response: Response, db: AsyncSession = Depends(get_db)):
    """
    Readiness probe — verifies PostgreSQL and Redis connections and records latencies.
    Returns HTTP 200 when all critical dependencies are ready, HTTP 503 if critical checks fail.
    """
    checks = {}
    latencies = {}

    # 1. Database check + latency
    t0 = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        latencies["database_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        latencies["database_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        checks["database"] = f"error: {exc}"

    # 2. Redis check + latency
    t1 = time.perf_counter()
    r_client = None
    try:
        r_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        await r_client.ping()
        latencies["redis_ms"] = round((time.perf_counter() - t1) * 1000, 2)
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        latencies["redis_ms"] = round((time.perf_counter() - t1) * 1000, 2)
        checks["redis"] = f"error: {exc}"
    finally:
        if r_client is not None:
            try:
                await r_client.aclose()
            except Exception:
                pass

    overall_ok = all(v == "ok" for v in checks.values())

    if not overall_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return success_response({
        "status": "ready" if overall_ok else "degraded",
        "checks": checks,
        "latencies": latencies,
        "env": settings.APP_ENV,
    })
