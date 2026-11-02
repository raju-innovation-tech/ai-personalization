"""
Offer engine tables (Phase 4).

* Offer            - a discount campaign with targeting rules and guardrails
* OfferInteraction - impressions / clicks reported by the storefront
* OfferRedemption  - one row per redeemed order (source of truth for budget limits)
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base
from app.database.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Offer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offers"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # percent_off | fixed_off | free_shipping
    offer_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(12, 2), default=0, server_default=text("0"), nullable=False)

    # --- guardrails ---
    max_discount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    min_order_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    max_redemptions: Mapped[int | None] = mapped_column(Integer, nullable=True)  # total budget
    max_per_customer: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)

    # draft | active | paused | ended
    status: Mapped[str] = mapped_column(
        String(20), default="draft", server_default="draft", index=True, nullable=False
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- targeting (empty list = everyone / every category) ---
    target_segments: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"), nullable=False)
    target_categories: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"), nullable=False)

    priority: Mapped[int] = mapped_column(Integer, default=50, server_default=text("50"), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<Offer {self.code} {self.status}>"


class OfferInteraction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offer_interactions"
    __table_args__ = (Index("ix_offer_interactions_offer_action", "offer_id", "action"),)

    offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("offers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    external_user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # impression | click
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)


class OfferRedemption(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offer_redemptions"
    __table_args__ = (UniqueConstraint("offer_id", "order_ref", name="uq_offer_redemptions_offer_order"),)

    offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("offers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    external_user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    order_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    order_value: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    free_shipping: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
