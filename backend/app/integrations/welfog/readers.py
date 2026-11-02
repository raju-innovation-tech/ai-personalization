"""
Read-only access to the Welfog databases.

Every source is read in "keyset" pages so a sync can be stopped and resumed safely:
  * sources with a modification time (orders, products) page on (timestamp, id), so a later
    change to an already-synced row (e.g. an order cancelled afterwards) is picked up again;
  * insert-only sources (carts, wishlists, reviews, user_events) page on id.
Re-sent rows are harmless: every event carries a stable idempotency key.

``build_select`` is pure (returns SQL text + parameters) so it is unit-tested without a database.
SQLAlchemy is only imported when a real database is used.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpec:
    name: str
    db: str  # "mysql" | "postgres"
    table: str
    id_col: str
    required: tuple[str, ...]
    optional: tuple[str, ...] = ()
    ts_cols: tuple[str, ...] = ()  # modification time = first non-null of these (COALESCE)


SOURCES: dict[str, SourceSpec] = {
    "products": SourceSpec(
        name="products", db="postgres", table="products", id_col="id", ts_cols=("updated_at", "created_at"),
        required=("id", "pro_id", "name", "category_name", "brand", "unit_price", "stock", "published", "approved", "hold", "block", "created_at", "updated_at"),
        optional=("description", "rating", "tags", "thumb_url", "thumbnail_img", "img_is_url", "sku", "color_name", "size",
                  "num_of_sale", "pro_features", "category_id"),
    ),
    "orders": SourceSpec(
        name="orders", db="mysql", table="orders", id_col="id", ts_cols=("updated_at", "created_at"),
        required=("id", "oid", "user_id", "product_id", "quantity", "price", "sp_price", "shipping_cost", "grand_total",
                  "payment_mode", "payment_status", "delivery_status", "return_status", "created_at", "updated_at"),
        optional=("coupon_discount", "coin_discount", "session_id", "platform"),
    ),
    "carts": SourceSpec(
        name="carts", db="mysql", table="carts", id_col="id",
        required=("id", "user_id", "product_id", "price", "quantity", "created_at"),
        optional=("session_id", "platform"),
    ),
    "wishlists": SourceSpec(
        name="wishlists", db="mysql", table="wishlists", id_col="id",
        required=("id", "user_id", "product_id", "created_at"),
    ),
    "reviews": SourceSpec(
        name="reviews", db="mysql", table="reviews", id_col="id",
        required=("id", "order_id", "product_id", "user_id", "rating", "created_at"),
    ),
    "user_events": SourceSpec(
        name="user_events", db="mysql", table="user_events", id_col="id",
        required=("id", "user_id", "event_type", "product_id", "occurred_at"),
        optional=("category_id", "search_query", "session_id", "platform", "metadata"),
    ),
}


def ts_expression(spec: SourceSpec) -> str | None:
    if not spec.ts_cols:
        return None
    return spec.ts_cols[0] if len(spec.ts_cols) == 1 else "COALESCE(" + ", ".join(spec.ts_cols) + ")"


def row_timestamp(spec: SourceSpec, row: dict):
    """Python twin of ts_expression (used to move the watermark)."""
    for col in spec.ts_cols:
        if row.get(col) is not None:
            return row[col]
    return None


def build_select(spec: SourceSpec, columns: list[str], after_ts, after_id, limit: int) -> tuple[str, dict]:
    """SQL (named :params) for the next page after the watermark (after_ts, after_id)."""
    ts = ts_expression(spec)
    params: dict = {"limit": int(limit)}
    if ts is None:
        where = f"{spec.id_col} > :last_id"
        params["last_id"] = int(after_id or 0)
        order = spec.id_col
    else:
        if after_ts is None:
            where = "1 = 1"
        else:
            where = f"({ts} > :last_ts OR ({ts} = :last_ts AND {spec.id_col} > :last_id))"
            params["last_ts"] = after_ts
            params["last_id"] = int(after_id or 0)
        order = f"{ts}, {spec.id_col}"
    sql = f"SELECT {', '.join(columns)} FROM {spec.table} WHERE {where} ORDER BY {order} LIMIT :limit"
    return sql, params


def pick_columns(spec: SourceSpec, available: set[str]) -> list[str]:
    """Required columns must exist; optional ones are read only when the table has them."""
    missing = [c for c in spec.required if c not in available]
    if missing:
        raise RuntimeError(f"{spec.db}.{spec.table} is missing expected column(s): {', '.join(missing)}")
    return list(spec.required) + [c for c in spec.optional if c in available]


def make_engine(url: str):
    from sqlalchemy import create_engine

    return create_engine(url, pool_pre_ping=True, pool_recycle=1800, future=True)


def available_columns(engine, spec: SourceSpec) -> set[str]:
    from sqlalchemy import inspect

    return {c["name"] for c in inspect(engine).get_columns(spec.table)}


def read_page(engine, spec: SourceSpec, columns: list[str], after_ts, after_id, limit: int) -> list[dict]:
    from sqlalchemy import text

    sql, params = build_select(spec, columns, after_ts, after_id, limit)
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql), params)]
