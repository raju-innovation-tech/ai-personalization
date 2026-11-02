"""
Customer mirror + derived intelligence profile.

We never own e-commerce customer identity - we mirror the external_user_id
(the existing platform's user id) and *derive* everything else from the
event stream. The profile columns are (re)computed by
`app.customers.service.recompute_profiles` (RFM scoring + segmentation).
"""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Numeric, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base
from app.database.models.base import TimestampMixin, UUIDPrimaryKeyMixin


def _zero() -> str:
    return text("0")


class EcommerceCustomer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ecommerce_customers"
    __table_args__ = (Index("ix_ecommerce_customers_last_seen_at", "last_seen_at"),)

    external_user_id: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- behaviour counters (within CUSTOMER_LOOKBACK_DAYS) ---
    total_events: Mapped[int] = mapped_column(Integer, default=0, server_default=_zero(), nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, server_default=_zero(), nullable=False)
    cart_add_count: Mapped[int] = mapped_column(Integer, default=0, server_default=_zero(), nullable=False)
    wishlist_count: Mapped[int] = mapped_column(Integer, default=0, server_default=_zero(), nullable=False)
    active_days: Mapped[int] = mapped_column(Integer, default=0, server_default=_zero(), nullable=False)

    # --- purchases ---
    order_count: Mapped[int] = mapped_column(Integer, default=0, server_default=_zero(), nullable=False)
    items_purchased: Mapped[int] = mapped_column(Integer, default=0, server_default=_zero(), nullable=False)
    return_count: Mapped[int] = mapped_column(Integer, default=0, server_default=_zero(), nullable=False)
    total_spend: Mapped[float] = mapped_column(
        Numeric(14, 2), default=0, server_default=_zero(), nullable=False
    )
    avg_order_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    first_order_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_order_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- RFM ---
    recency_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    r_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    f_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    m_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    rfm_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    segment: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)

    # --- interests ---
    favorite_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    favorite_brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<EcommerceCustomer {self.external_user_id}>"
