"""Process-level facts (when this API process started)."""
from datetime import datetime, timezone

STARTED_AT = datetime.now(timezone.utc)


def uptime_seconds() -> int:
    return int((datetime.now(timezone.utc) - STARTED_AT).total_seconds())
