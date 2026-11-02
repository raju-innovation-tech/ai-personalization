"""phase 6: A/B testing tables

Revision ID: e85d0b3c6e54
Revises: d63b8f1a4c32
Create Date: 2026-10-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e85d0b3c6e54"
down_revision: Union[str, None] = "d63b8f1a4c32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("hypothesis", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("primary_metric", sa.String(length=20), server_default="conversion", nullable=False),
        sa.Column("traffic_percent", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.Column("variants", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("winner_key", sa.String(length=40), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_experiments_key"), "experiments", ["key"], unique=True)
    op.create_index(op.f("ix_experiments_status"), "experiments", ["status"], unique=False)

    op.create_table(
        "experiment_exposures",
        sa.Column("experiment_id", sa.UUID(), nullable=False),
        sa.Column("external_user_id", sa.String(length=128), nullable=False),
        sa.Column("variant_key", sa.String(length=40), nullable=False),
        sa.Column("first_exposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id", "external_user_id", name="uq_experiment_exposures_experiment_user"),
    )
    op.create_index(op.f("ix_experiment_exposures_experiment_id"), "experiment_exposures", ["experiment_id"], unique=False)
    op.create_index(
        op.f("ix_experiment_exposures_external_user_id"), "experiment_exposures", ["external_user_id"], unique=False
    )
    op.create_index(
        "ix_experiment_exposures_experiment_variant", "experiment_exposures", ["experiment_id", "variant_key"], unique=False
    )


def downgrade() -> None:
    op.drop_table("experiment_exposures")
    op.drop_table("experiments")
