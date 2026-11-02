"""
A/B testing tables (Phase 6).

* Experiment         - what is tested, on whom (traffic %), with which variants (JSON list)
* ExperimentExposure - the first time a customer was served a variant; outcomes are counted from then on
"""
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base
from app.database.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Experiment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiments"

    key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)

    # recommendations | offers
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    # draft | running | paused | completed
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft", index=True, nullable=False)
    # conversion | click | revenue
    primary_metric: Mapped[str] = mapped_column(String(20), default="conversion", server_default="conversion", nullable=False)
    traffic_percent: Mapped[int] = mapped_column(Integer, default=100, server_default=text("100"), nullable=False)
    # [{"key": "control", "name": "...", "weight": 50, "config": {...}}, ...]; the first entry is the control
    variants: Mapped[list] = mapped_column(JSON, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    winner_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<Experiment {self.key} {self.status}>"


class ExperimentExposure(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiment_exposures"
    __table_args__ = (
        UniqueConstraint("experiment_id", "external_user_id", name="uq_experiment_exposures_experiment_user"),
        Index("ix_experiment_exposures_experiment_variant", "experiment_id", "variant_key"),
    )

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    external_user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    variant_key: Mapped[str] = mapped_column(String(40), nullable=False)
    first_exposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
