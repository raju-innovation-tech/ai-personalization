"""phase 2: richer product catalog + recommendation logs

Revision ID: b41f8c2d9a10
Revises: e7b04b4e36e2
Create Date: 2026-10-07 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b41f8c2d9a10"
down_revision: Union[str, None] = "e7b04b4e36e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("image_url", sa.String(length=1000), nullable=True))
    op.add_column("products", sa.Column("rating", sa.Numeric(precision=3, scale=2), nullable=True))
    op.add_column("products", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column(
        "products",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "products",
        sa.Column("in_stock", sa.Boolean(), server_default=sa.true(), nullable=False),
    )

    # Backfill from the Phase 1 free-form `attributes` JSON (seed data stored these there).
    op.execute(
        """
        UPDATE products SET
            in_stock = COALESCE((attributes::jsonb ->> 'in_stock')::boolean, true),
            rating   = CASE WHEN (attributes::jsonb ->> 'rating') ~ '^[0-5](\\.[0-9]+)?$'
                            THEN (attributes::jsonb ->> 'rating')::numeric ELSE NULL END,
            tags     = CASE WHEN jsonb_typeof(attributes::jsonb -> 'tags') = 'array'
                            THEN (attributes::jsonb -> 'tags')::json ELSE NULL END
        WHERE attributes IS NOT NULL
        """
    )

    op.create_table(
        "recommendation_logs",
        sa.Column("algorithm", sa.String(length=50), nullable=False),
        sa.Column("external_user_id", sa.String(length=128), nullable=True),
        sa.Column("product_id", sa.String(length=128), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recommendation_logs_algorithm"), "recommendation_logs", ["algorithm"], unique=False)
    op.create_index(
        op.f("ix_recommendation_logs_external_user_id"), "recommendation_logs", ["external_user_id"], unique=False
    )
    op.create_index(op.f("ix_recommendation_logs_created_at"), "recommendation_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_recommendation_logs_created_at"), table_name="recommendation_logs")
    op.drop_index(op.f("ix_recommendation_logs_external_user_id"), table_name="recommendation_logs")
    op.drop_index(op.f("ix_recommendation_logs_algorithm"), table_name="recommendation_logs")
    op.drop_table("recommendation_logs")
    op.drop_column("products", "in_stock")
    op.drop_column("products", "is_active")
    op.drop_column("products", "tags")
    op.drop_column("products", "rating")
    op.drop_column("products", "image_url")
    op.drop_column("products", "description")
