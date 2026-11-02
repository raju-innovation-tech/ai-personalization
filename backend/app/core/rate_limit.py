"""
Production rate limiter using Redis with automatic in-memory sliding fallback.
"""
from collections import defaultdict
import os
import threading
import time
from typing import Dict, List

from fastapi import Request
from starlette.exceptions import HTTPException

from app.core.config import settings
from app.core.health import get_redis
from app.core.logging import get_logger

logger = get_logger("app.rate_limit")


class InMemoryFallbackLimiter:
    """Thread-safe fallback limiter if Redis is offline."""

    def __init__(self):
        self._lock = threading.Lock()
        self._records: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            timestamps = self._records[key]
            # Prune expired timestamps
            self._records[key] = [t for t in timestamps if t > cutoff]
            current_count = len(self._records[key])
            if current_count >= limit:
                oldest = self._records[key][0]
                retry_after = max(1, int(oldest + window_seconds - now))
                return False, retry_after

            self._records[key].append(now)
            return True, 0


_fallback_limiter = InMemoryFallbackLimiter()


class RateLimiter:
    """
    FastAPI dependency to enforce rate limiting on sensitive endpoints.
    Uses client IP or identity token to partition rate quotas.
    """

    def __init__(self, key_prefix: str, limit: int, window_seconds: int = 60):
        self.key_prefix = key_prefix
        self.limit = limit
        self.window_seconds = window_seconds

    def _get_client_identifier(self, request: Request) -> str:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        return client_ip

    async def __call__(self, request: Request) -> None:
        if os.environ.get("PYTEST_CURRENT_TEST") or getattr(settings, "APP_ENV", "") == "test":
            return

        client_id = self._get_client_identifier(request)
        rate_key = f"rl:{self.key_prefix}:{client_id}"

        try:
            redis_client = get_redis()
            current_count = await redis_client.incr(rate_key)
            if current_count == 1:
                await redis_client.expire(rate_key, self.window_seconds)

            if current_count > self.limit:
                ttl = await redis_client.ttl(rate_key)
                retry_after = max(1, ttl if ttl > 0 else self.window_seconds)
                logger.warning(
                    "rate_limit_exceeded",
                    prefix=self.key_prefix,
                    client=client_id,
                    count=current_count,
                    limit=self.limit,
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )
        except HTTPException:
            raise
        except Exception as exc:
            # Fallback to local memory limiter if Redis connection fails
            logger.debug("rate_limit_redis_failed_using_fallback", error=str(exc))
            allowed, retry_after = _fallback_limiter.is_allowed(rate_key, self.limit, self.window_seconds)
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )
