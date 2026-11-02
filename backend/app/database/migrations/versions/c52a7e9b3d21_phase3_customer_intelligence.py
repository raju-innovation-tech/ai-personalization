"""phase 3: customer intelligence profile columns

Revision ID: c52a7e9b3d21
Revises: b41f8c2d9a10
Create Date: 2026-10-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c52a7e9b3d21"
down_revision: Union[str, None] = "b41f8c2d9a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INT_COLUMNS = (
    "total_events",
    "view_count",
    "cart_add_count",
    "wishlist_count",
    "active_days",
    "order_count",
    "items_purchased",
    "return_count",
)


def upgrade() -> None:
    for name in _INT_COLUMNS:
        op.add_column(
            "ecommerce_customers",
            sa.Column(name, sa.Integer(), server_default=sa.text("0"), nullable=False),
        )
    op.add_column(
        "ecommerce_customers",
        sa.Column("total_spend", sa.Numeric(precision=14, scale=2), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("ecommerce_customers", sa.Column("avg_order_value", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("ecommerce_customers", sa.Column("first_order_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ecommerce_customers", sa.Column("last_order_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ecommerce_customers", sa.Column("recency_days", sa.Integer(), nullable=True))
    op.add_column("ecommerce_customers", sa.Column("r_score", sa.SmallInteger(), nullable=True))
    op.add_column("ecommerce_customers", sa.Column("f_score", sa.SmallInteger(), nullable=True))
    op.add_column("ecommerce_customers", sa.Column("m_score", sa.SmallInteger(), nullable=True))
    op.add_column("ecommerce_customers", sa.Column("rfm_code", sa.String(length=3), nullable=True))
    op.add_column("ecommerce_customers", sa.Column("segment", sa.String(length=40), nullable=True))
    op.add_column("ecommerce_customers", sa.Column("favorite_category", sa.String(length=255), nullable=True))
    op.add_column("ecommerce_customers", sa.Column("favorite_brand", sa.String(length=255), nullable=True))
    op.add_column("ecommerce_customers", sa.Column("profile_computed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_ecommerce_customers_segment"), "ecommerce_customers", ["segment"], unique=False)
    op.create_index(op.f("ix_ecommerce_customers_last_seen_at"), "ecommerce_customers", ["last_seen_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ecommerce_customers_last_seen_at"), table_name="ecommerce_customers")
    op.drop_index(op.f("ix_ecommerce_customers_segment"), table_name="ecommerce_customers")
    for name in (
        "profile_computed_at", "favorite_brand", "favorite_category", "segment", "rfm_code", "m_score",
        "f_score", "r_score", "recency_days", "last_order_at", "first_order_at", "avg_order_value", "total_spend",
    ):
        op.drop_column("ecommerce_customers", name)
    for name in reversed(_INT_COLUMNS):
        op.drop_column("ecommerce_customers", name)
