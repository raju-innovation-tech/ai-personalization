import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.responses import ApiError, error_response
from app.analytics.router import router as analytics_router
from app.customers.router import router as customers_router
from app.customers.scheduler import profile_refresh_loop
from app.events.router import router as events_router
from app.experiments.router import router as experiments_router
from app.integrations.router import router as integrations_router
from app.offers.router import router as offers_router
from app.products.router import router as products_router
from app.recommendations.router import router as recommendations_router
from app.search.router import router as search_router
from app.segments.router import router as segments_router
from app.system.router import router as system_router
from app.users.router import router as users_router
from app.core.health import router as health_router
from app.core.metrics import metrics_router
from app.core.middleware import (
    MaxBodySizeMiddleware,
    RequestTracingMiddleware,
    SecurityHeadersMiddleware,
)
from app.ml.router import router as ml_router

configure_logging()
logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Production security validation
    if settings.APP_ENV == "production":
        insecure_keys = {"CHANGE_ME_TO_A_LONG_RANDOM_SECRET", "test-secret-key-for-pytest-only", ""}
        if settings.JWT_SECRET_KEY in insecure_keys or len(settings.JWT_SECRET_KEY) < 32:
            raise RuntimeError("CRITICAL: Insecure or short JWT_SECRET_KEY detected in production!")
        if settings.DEBUG:
            logger.warning("production_debug_warning", message="DEBUG is enabled in production!")

    logger.info("app_startup", env=settings.APP_ENV, version="0.8.0")
    refresher = None
    if settings.CUSTOMER_PROFILE_REFRESH_MINUTES > 0:
        refresher = asyncio.create_task(profile_refresh_loop())
    yield
    if refresher is not None:
        refresher.cancel()
        try:
            await refresher
        except asyncio.CancelledError:
            pass
    logger.info("app_shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version="0.8.0",
    description="AI Personalization & Offer Engine — Production REST API for e-commerce integration.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Middleware stack (executed in reverse order of registration)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(MaxBodySizeMiddleware)
app.add_middleware(RequestTracingMiddleware)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(exc.code, exc.message),
    )


_HTTP_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    429: "RATE_LIMITED",
}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Unknown routes, wrong methods, etc. -> same envelope as every other error."""
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            _HTTP_ERROR_CODES.get(exc.status_code, "HTTP_ERROR"), str(exc.detail)
        ),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = [
        {
            "field": ".".join(str(part) for part in err.get("loc", ()) if part != "body"),
            "message": err.get("msg", "Invalid value"),
        }
        for err in exc.errors()
    ]
    first = details[0] if details else {"field": "", "message": "Invalid request"}
    message = f"{first['field']}: {first['message']}" if first["field"] else first["message"]
    return JSONResponse(
        status_code=422,
        content=error_response("VALIDATION_ERROR", message, details=details),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=error_response("INTERNAL_SERVER_ERROR", "An unexpected error occurred"),
    )


app.include_router(health_router, prefix=settings.API_V1_PREFIX)
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(events_router, prefix=settings.API_V1_PREFIX)
app.include_router(products_router, prefix=settings.API_V1_PREFIX)
app.include_router(recommendations_router, prefix=settings.API_V1_PREFIX)
app.include_router(analytics_router, prefix=settings.API_V1_PREFIX)
app.include_router(customers_router, prefix=settings.API_V1_PREFIX)
app.include_router(segments_router, prefix=settings.API_V1_PREFIX)
app.include_router(offers_router, prefix=settings.API_V1_PREFIX)
app.include_router(experiments_router, prefix=settings.API_V1_PREFIX)
app.include_router(integrations_router, prefix=settings.API_V1_PREFIX)
app.include_router(system_router, prefix=settings.API_V1_PREFIX)
app.include_router(users_router, prefix=settings.API_V1_PREFIX)
app.include_router(search_router, prefix=settings.API_V1_PREFIX)
app.include_router(ml_router, prefix=settings.API_V1_PREFIX)
app.include_router(metrics_router)
app.include_router(metrics_router, prefix=settings.API_V1_PREFIX)
