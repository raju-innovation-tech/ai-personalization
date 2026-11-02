from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from app.database.models.event import EventType, Platform


def _contains_nul(value) -> bool:
    """PostgreSQL text/JSONB cannot store the NUL character."""
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_contains_nul(k) or _contains_nul(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_nul(v) for v in value)
    return False


class EventIn(BaseModel):
    event_type: EventType
    external_user_id: str = Field(..., min_length=1, max_length=128)
    product_id: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    platform: Platform = Platform.UNKNOWN
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(
        default=None,
        max_length=255,
        description="Optional. If omitted, one is derived from the event fields.",
    )

    @field_validator("external_user_id", "product_id", "session_id", "idempotency_key", "metadata")
    @classmethod
    def reject_nul_characters(cls, v):
        if _contains_nul(v):
            raise ValueError("value must not contain the NUL character")
        return v

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, v: datetime | None) -> datetime:
        if v is None:
            return datetime.now(timezone.utc)
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class EventBatchIn(BaseModel):
    events: list[EventIn] = Field(..., min_length=1, max_length=500)


class EventAcceptedOut(BaseModel):
    idempotency_key: str
    status: str  # "accepted" | "duplicate"


class EventBatchResultOut(BaseModel):
    accepted: int
    duplicates: int
    rejected: int
    results: list[EventAcceptedOut]
    errors: list[dict]
