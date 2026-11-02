"""
Raw customer behavior event, as sent by the existing e-commerce platform.

Idempotency: the ingesting client is expected to supply a stable
idempotency_key per logical event (or we derive one — see events service).
A unique constraint prevents duplicate processing on retry.
"""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base
from app.database.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class EventType(str, enum.Enum):
    PRODUCT_VIEW = "PRODUCT_VIEW"
    PRODUCT_SEARCH = "PRODUCT_SEARCH"
    CATEGORY_VIEW = "CATEGORY_VIEW"
    WISHLIST_ADD = "WISHLIST_ADD"
    WISHLIST_REMOVE = "WISHLIST_REMOVE"
    ADD_TO_CART = "ADD_TO_CART"
    REMOVE_FROM_CART = "REMOVE_FROM_CART"
    CHECKOUT_STARTED = "CHECKOUT_STARTED"
    PURCHASE = "PURCHASE"
    PURCHASE_CANCELLED = "PURCHASE_CANCELLED"
    RETURN = "RETURN"
    PRODUCT_REVIEW = "PRODUCT_REVIEW"
    OFFER_VIEW = "OFFER_VIEW"
    OFFER_CLICK = "OFFER_CLICK"
    OFFER_REDEEM = "OFFER_REDEEM"
    RECOMMENDATION_VIEW = "RECOMMENDATION_VIEW"
    RECOMMENDATION_CLICK = "RECOMMENDATION_CLICK"


class Platform(str, enum.Enum):
    WEB = "web"
    MOBILE = "mobile"
    IOS = "ios"
    ANDROID = "android"
    UNKNOWN = "unknown"


class UserEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_events"
    __table_args__ = (
        Index("ix_user_events_user_type_time", "external_user_id", "event_type", "occurred_at"),
    )

    external_user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType, name="event_type"), index=True, nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, name="event_platform"), default=Platform.UNKNOWN, nullable=False
    )
    event_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    def __repr__(self) -> str:
        return f"<UserEvent {self.event_type} user={self.external_user_id}>"
