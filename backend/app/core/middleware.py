"""
Production middleware: Security headers, request tracing, payload limit, and observability metrics.
"""
import time
import uuid

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import metrics_collector
from app.core.responses import error_response

logger = get_logger("app.middleware")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Applies OWASP-recommended security headers to all HTTP responses."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        if settings.ENABLE_SECURITY_HEADERS:
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("X-XSS-Protection", "1; mode=block")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            response.headers.setdefault(
                "Permissions-Policy",
                "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()",
            )
            # Apply HSTS in production or when connection is HTTPS
            if settings.APP_ENV == "production" or request.url.scheme == "https":
                response.headers.setdefault(
                    "Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload"
                )

        return response


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Enforces maximum payload size limit to guard against large-payload DoS attacks."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
                if length > settings.MAX_CONTENT_LENGTH_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content=error_response(
                            "PAYLOAD_TOO_LARGE",
                            f"Request body exceeds maximum allowed size ({settings.MAX_CONTENT_LENGTH_BYTES} bytes)",
                        ),
                    )
            except ValueError:
                pass

        return await call_next(request)


class RequestTracingMiddleware(BaseHTTPMiddleware):
    """Assigns unique X-Request-ID, logs completion latency, and updates Prometheus metrics."""

    async def dispatch(self, request: Request, call_next):
        # Honor inbound X-Request-ID (e.g. from upstream Nginx or gateway) or generate fresh UUID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start = time.perf_counter()

        response: Response = await call_next(request)

        duration_sec = time.perf_counter() - start
        duration_ms = round(duration_sec * 1000, 2)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        # Record metrics for observability
        normalized_path = request.url.path
        # Normalize paths with IDs to keep metric cardinality low
        if "/similar/" in normalized_path:
            normalized_path = "/api/v1/recommendations/similar/:id"
        elif "/frequently-bought/" in normalized_path:
            normalized_path = "/api/v1/recommendations/frequently-bought/:id"
        elif "/user/" in normalized_path and "recommendations" in normalized_path:
            normalized_path = "/api/v1/recommendations/user/:id"
        elif "/user/" in normalized_path and "offers" in normalized_path:
            normalized_path = "/api/v1/offers/user/:id"
        elif "/customers/" in normalized_path:
            normalized_path = "/api/v1/customers/:id"

        metrics_collector.inc_counter(
            "http_requests_total",
            1.0,
            {
                "method": request.method,
                "path": normalized_path,
                "status": str(response.status_code),
            },
        )
        metrics_collector.observe_duration(
            "http_request_duration_seconds",
            duration_sec,
            {"method": request.method, "path": normalized_path},
        )

        logger.info(
            "request_completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=duration_ms,
        )

        return response
