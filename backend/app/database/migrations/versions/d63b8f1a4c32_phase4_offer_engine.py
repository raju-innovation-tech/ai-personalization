"""phase 4: offer engine tables

Revision ID: d63b8f1a4c32
Revises: c52a7e9b3d21
Create Date: 2026-10-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d63b8f1a4c32"
down_revision: Union[str, None] = "c52a7e9b3d21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "offers",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("offer_type", sa.String(length=20), nullable=False),
        sa.Column("value", sa.Numeric(precision=12, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("max_discount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("min_order_value", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("max_redemptions", sa.Integer(), nullable=True),
        sa.Column("max_per_customer", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_segments", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("target_categories", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default=sa.text("50"), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_offers_code"), "offers", ["code"], unique=True)
    op.create_index(op.f("ix_offers_status"), "offers", ["status"], unique=False)

    op.create_table(
        "offer_interactions",
        sa.Column("offer_id", sa.UUID(), nullable=False),
        sa.Column("external_user_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(op.f("ix_offer_interactions_offer_id"), "offer_interactions", ["offer_id"], unique=False)
    op.create_index(
        op.f("ix_offer_interactions_external_user_id"), "offer_interactions", ["external_user_id"], unique=False
    )
    op.create_index(op.f("ix_offer_interactions_occurred_at"), "offer_interactions", ["occurred_at"], unique=False)
    op.create_index("ix_offer_interactions_offer_action", "offer_interactions", ["offer_id", "action"], unique=False)

    op.create_table(
        "offer_redemptions",
        sa.Column("offer_id", sa.UUID(), nullable=False),
        sa.Column("external_user_id", sa.String(length=128), nullable=False),
        sa.Column("order_ref", sa.String(length=128), nullable=False),
        sa.Column("order_value", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("free_shipping", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offer_id", "order_ref", name="uq_offer_redemptions_offer_order"),
    )
    op.create_index(op.f("ix_offer_redemptions_offer_id"), "offer_redemptions", ["offer_id"], unique=False)
    op.create_index(
        op.f("ix_offer_redemptions_external_user_id"), "offer_redemptions", ["external_user_id"], unique=False
    )
    op.create_index(op.f("ix_offer_redemptions_redeemed_at"), "offer_redemptions", ["redeemed_at"], unique=False)


def downgrade() -> None:
    op.drop_table("offer_redemptions")
    op.drop_table("offer_interactions")
    op.drop_table("offers")
