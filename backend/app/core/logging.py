"""
Structured logging configuration.

Uses structlog to emit JSON logs in production and pretty console
logs in development. NEVER log passwords, tokens, or raw PII — call
sites are responsible for redacting sensitive fields before logging,
and this module intentionally does not provide a way to bypass that.
"""
import logging
import sys

import structlog

from app.core.config import settings

SENSITIVE_KEYS = {"password", "hashed_password", "token", "access_token", "refresh_token", "authorization"}


def _redact_processor(_, __, event_dict):
    for key in list(event_dict.keys()):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "***REDACTED***"
    return event_dict


def configure_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    )

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_processor,
    ]

    if settings.APP_ENV == "production":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "app"):
    return structlog.get_logger(name)
