"""
One row per recommendation API call served. Powers the "Recommendations
Served" KPI and per-algorithm usage stats in the admin dashboard.
"""
from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base
from app.database.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class RecommendationLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recommendation_logs"
    __table_args__ = (Index("ix_recommendation_logs_created_at", "created_at"),)

    algorithm: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    external_user_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<RecommendationLog {self.algorithm} n={self.result_count}>"
