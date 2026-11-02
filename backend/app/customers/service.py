"""Database side of customer intelligence: recompute profiles, query them."""
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import Date, case, cast, distinct, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.customers.intelligence import (
    CustomerStats,
    build_profiles,
    purchase_quantity,
    purchase_value,
    segment_counts,
)
from app.database.models.customer import EcommerceCustomer
from app.database.models.event import EventType, UserEvent
from app.database.models.product import Product
from app.recommendations.engine import EVENT_WEIGHTS
from app.segments.definitions import SEGMENT_BY_KEY

logger = get_logger(__name__)

ADVISORY_LOCK_KEY = 7_300_301  # one recompute at a time, across all API workers

_PROFILE_COLUMNS = (
    "total_events", "view_count", "cart_add_count", "wishlist_count", "order_count", "items_purchased",
    "return_count", "total_spend", "avg_order_value", "first_order_at", "last_order_at", "active_days",
    "recency_days", "r_score", "f_score", "m_score", "rfm_code", "segment", "favorite_category",
    "favorite_brand", "profile_computed_at",
)


def _min_dt(a: datetime | None, b: datetime | None) -> datetime | None:
    return b if a is None else a if b is None else min(a, b)


def _max_dt(a: datetime | None, b: datetime | None) -> datetime | None:
    return b if a is None else a if b is None else max(a, b)


async def recompute_profiles(db: AsyncSession) -> dict | None:
    """
    Rebuild every customer's profile, RFM scores and segment from the event stream.
    Returns a summary, or None when another recompute is already running.
    Commits (which also releases the advisory lock).
    """
    locked = (await db.execute(select(func.pg_try_advisory_xact_lock(ADVISORY_LOCK_KEY)))).scalar_one()
    if not locked:
        await db.rollback()
        return None

    started = time.perf_counter()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.CUSTOMER_LOOKBACK_DAYS)
    in_window = UserEvent.occurred_at >= cutoff

    stats: dict[str, CustomerStats] = {}
    for uid, first, last in (
        await db.execute(
            select(EcommerceCustomer.external_user_id, EcommerceCustomer.first_seen_at, EcommerceCustomer.last_seen_at)
        )
    ).all():
        stats[uid] = CustomerStats(user_id=uid, first_seen=first, last_seen=last)

    # 1) behaviour counters
    day = cast(func.timezone("UTC", UserEvent.occurred_at), Date)
    behaviour = await db.execute(
        select(
            UserEvent.external_user_id,
            func.count(),
            func.count().filter(UserEvent.event_type == EventType.PRODUCT_VIEW),
            func.count().filter(UserEvent.event_type == EventType.ADD_TO_CART),
            func.count().filter(UserEvent.event_type == EventType.WISHLIST_ADD),
            func.count(distinct(day)),
            func.min(UserEvent.occurred_at),
            func.max(UserEvent.occurred_at),
        )
        .where(in_window)
        .group_by(UserEvent.external_user_id)
    )
    for uid, total, views, carts, wishes, days, first, last in behaviour.all():
        s = stats.setdefault(uid, CustomerStats(user_id=uid))
        s.total_events, s.views, s.cart_adds, s.wishlist_adds, s.active_days = total, views, carts, wishes, days
        s.first_seen = _min_dt(s.first_seen, first)
        s.last_seen = _max_dt(s.last_seen, last)

    # 2) purchases -> orders (one order = one session, or one day when there is no session id)
    order_keys: dict[str, set[str]] = defaultdict(set)
    purchases = await db.execute(
        select(
            UserEvent.external_user_id, UserEvent.session_id, UserEvent.occurred_at,
            UserEvent.event_metadata, Product.price,
        )
        .select_from(UserEvent)
        .outerjoin(Product, Product.external_product_id == UserEvent.product_id)
        .where(UserEvent.event_type == EventType.PURCHASE, in_window)
    )
    for uid, session_id, occurred_at, metadata, price in purchases.all():
        s = stats.setdefault(uid, CustomerStats(user_id=uid))
        order_keys[uid].add(session_id or occurred_at.astimezone(timezone.utc).date().isoformat())
        s.spend += purchase_value(metadata, float(price) if price is not None else None)
        s.items += purchase_quantity(metadata)
        s.first_order = _min_dt(s.first_order, occurred_at)
        s.last_order = _max_dt(s.last_order, occurred_at)
    for uid, keys in order_keys.items():
        stats[uid].orders = len(keys)

    # 3) refunds reduce spend
    refunds = await db.execute(
        select(UserEvent.external_user_id, UserEvent.event_metadata, Product.price)
        .select_from(UserEvent)
        .outerjoin(Product, Product.external_product_id == UserEvent.product_id)
        .where(UserEvent.event_type.in_([EventType.PURCHASE_CANCELLED, EventType.RETURN]), in_window)
    )
    for uid, metadata, price in refunds.all():
        s = stats.setdefault(uid, CustomerStats(user_id=uid))
        s.returns += 1
        s.spend -= purchase_value(metadata, float(price) if price is not None else None)

    # 4) favourite category / brand (weighted by how strong each behaviour is)
    weight = case(
        *[(UserEvent.event_type == EventType[name], w) for name, w in EVENT_WEIGHTS.items()
          if w > 0 and name in EventType.__members__],
        else_=0,
    )
    by_category: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_brand: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    interests = await db.execute(
        select(UserEvent.external_user_id, Product.category, Product.brand, func.sum(weight))
        .select_from(UserEvent)
        .join(Product, Product.external_product_id == UserEvent.product_id)
        .where(in_window)
        .group_by(UserEvent.external_user_id, Product.category, Product.brand)
    )
    for uid, category, brand, total in interests.all():
        if category:
            by_category[uid][category] += float(total or 0)
        if brand:
            by_brand[uid][brand] += float(total or 0)
    for uid, s in stats.items():
        if uid in by_category:
            s.favorite_category = max(by_category[uid], key=lambda c: (by_category[uid][c], c))
        if uid in by_brand:
            s.favorite_brand = max(by_brand[uid], key=lambda b: (by_brand[uid][b], b))

    profiles = build_profiles(list(stats.values()), now=now, active_days=settings.CUSTOMER_ACTIVE_DAYS)

    # 5) store (insert missing customers, update the rest)
    for start in range(0, len(profiles), 400):
        rows = [
            {
                "id": uuid.uuid4(),
                "external_user_id": p["user_id"],
                "first_seen_at": p["first_seen_at"],
                "last_seen_at": p["last_seen_at"],
                **{column: p[column] for column in _PROFILE_COLUMNS},
            }
            for p in profiles[start : start + 400]
        ]
        stmt = pg_insert(EcommerceCustomer).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[EcommerceCustomer.external_user_id],
            set_={
                **{column: getattr(stmt.excluded, column) for column in _PROFILE_COLUMNS},
                "first_seen_at": func.least(EcommerceCustomer.first_seen_at, stmt.excluded.first_seen_at),
                "last_seen_at": func.greatest(EcommerceCustomer.last_seen_at, stmt.excluded.last_seen_at),
                "updated_at": func.now(),
            },
        )
        await db.execute(stmt)
    await db.commit()

    summary = {
        "customers": len(profiles),
        "buyers": sum(1 for p in profiles if p["order_count"] > 0),
        "segments": segment_counts(profiles),
        "computed_at": now.isoformat(),
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
    }
    logger.info("customer_profiles_recomputed", **{k: v for k, v in summary.items() if k != "segments"})
    return summary


# ---------------------------------------------------------------- serialisation
def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _num(value) -> float | None:
    return float(value) if value is not None else None


def segment_ref(key: str | None) -> dict | None:
    if key is None:
        return None
    definition = SEGMENT_BY_KEY.get(key)
    return {"key": key, "name": definition.name if definition else key}


def customer_out(row: EcommerceCustomer, *, detail: bool = False) -> dict:
    data = {
        "customer_id": row.external_user_id,
        "segment": segment_ref(row.segment),
        "first_seen_at": _iso(row.first_seen_at),
        "last_seen_at": _iso(row.last_seen_at),
        "stats": {
            "events": row.total_events,
            "views": row.view_count,
            "cart_adds": row.cart_add_count,
            "wishlist_adds": row.wishlist_count,
            "active_days": row.active_days,
            "orders": row.order_count,
            "items_purchased": row.items_purchased,
            "returns": row.return_count,
            "total_spend": _num(row.total_spend) or 0.0,
            "avg_order_value": _num(row.avg_order_value),
            "first_order_at": _iso(row.first_order_at),
            "last_order_at": _iso(row.last_order_at),
            "recency_days": row.recency_days,
        },
        "rfm": {"r": row.r_score, "f": row.f_score, "m": row.m_score, "code": row.rfm_code},
        "favorite_category": row.favorite_category,
        "favorite_brand": row.favorite_brand,
        "profile_computed_at": _iso(row.profile_computed_at),
    }
    if detail and row.segment in SEGMENT_BY_KEY:
        definition = SEGMENT_BY_KEY[row.segment]
        data["segment"] = {
            "key": definition.key,
            "name": definition.name,
            "description": definition.description,
            "action": definition.action,
        }
    return data


# ---------------------------------------------------------------------- queries
_SORTS = {
    "last_seen": EcommerceCustomer.last_seen_at,
    "spend": EcommerceCustomer.total_spend,
    "orders": EcommerceCustomer.order_count,
    "recency": EcommerceCustomer.recency_days,
    "events": EcommerceCustomer.total_events,
    "rfm": (
        func.coalesce(EcommerceCustomer.r_score, 0)
        + func.coalesce(EcommerceCustomer.f_score, 0)
        + func.coalesce(EcommerceCustomer.m_score, 0)
    ),
}


async def list_customers(
    db: AsyncSession, *, q: str | None, segment: str | None, sort: str, descending: bool, page: int, page_size: int
) -> tuple[list[EcommerceCustomer], int]:
    def filtered(query):
        if q:
            query = query.where(EcommerceCustomer.external_user_id.ilike(f"%{q.strip()}%"))
        if segment:
            query = query.where(EcommerceCustomer.segment == segment)
        return query

    total = (await db.execute(filtered(select(func.count()).select_from(EcommerceCustomer)))).scalar_one()
    column = _SORTS[sort]
    order = column.desc().nulls_last() if descending else column.asc().nulls_last()
    rows = (
        await db.execute(
            filtered(select(EcommerceCustomer))
            .order_by(order, EcommerceCustomer.external_user_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def get_customer(db: AsyncSession, external_user_id: str) -> EcommerceCustomer | None:
    return (
        await db.execute(select(EcommerceCustomer).where(EcommerceCustomer.external_user_id == external_user_id))
    ).scalar_one_or_none()


async def customer_timeline(db: AsyncSession, external_user_id: str, page: int, page_size: int) -> tuple[list[dict], int]:
    total = (
        await db.execute(select(func.count()).select_from(UserEvent).where(UserEvent.external_user_id == external_user_id))
    ).scalar_one()
    rows = (
        await db.execute(
            select(
                UserEvent.event_type, UserEvent.product_id, UserEvent.occurred_at, UserEvent.session_id,
                UserEvent.platform, Product.name, Product.category,
            )
            .select_from(UserEvent)
            .outerjoin(Product, Product.external_product_id == UserEvent.product_id)
            .where(UserEvent.external_user_id == external_user_id)
            .order_by(UserEvent.occurred_at.desc(), UserEvent.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = [
        {
            "event_type": event_type.name,
            "product_id": product_id,
            "product_name": name,
            "category": category,
            "occurred_at": _iso(occurred_at),
            "session_id": session_id,
            "platform": platform.value if hasattr(platform, "value") else str(platform),
        }
        for event_type, product_id, occurred_at, session_id, platform, name, category in rows
    ]
    return items, int(total)


async def customer_overview(db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=settings.CUSTOMER_ACTIVE_DAYS)
    C = EcommerceCustomer

    async def scalar(query):
        return (await db.execute(query)).scalar_one()

    customers = int(await scalar(select(func.count()).select_from(C)))
    buyers = int(await scalar(select(func.count()).select_from(C).where(C.order_count > 0)))
    repeat = int(await scalar(select(func.count()).select_from(C).where(C.order_count >= 2)))
    active = int(await scalar(select(func.count()).select_from(C).where(C.last_seen_at >= since)))
    new = int(await scalar(select(func.count()).select_from(C).where(C.first_seen_at >= since)))
    revenue = float(await scalar(select(func.coalesce(func.sum(C.total_spend), 0))))
    orders = int(await scalar(select(func.coalesce(func.sum(C.order_count), 0))))
    computed_at = await scalar(select(func.max(C.profile_computed_at)))

    top = (
        await db.execute(
            select(C.external_user_id, C.total_spend, C.order_count, C.segment)
            .where(C.total_spend > 0)
            .order_by(C.total_spend.desc(), C.external_user_id)
            .limit(5)
        )
    ).all()

    return {
        "totals": {
            "customers": customers,
            "buyers": buyers,
            "repeat_buyers": repeat,
            "repeat_rate": round(repeat / buyers, 4) if buyers else None,
            "active_customers": active,
            "new_customers": new,
            "revenue": round(revenue, 2),
            "orders": orders,
            "avg_order_value": round(revenue / orders, 2) if orders else None,
        },
        "active_days": settings.CUSTOMER_ACTIVE_DAYS,
        "profiles_computed_at": _iso(computed_at),
        "top_spenders": [
            {"customer_id": uid, "total_spend": float(spend), "orders": n, "segment": segment_ref(seg)}
            for uid, spend, n, seg in top
        ],
    }


async def segment_overview(db: AsyncSession) -> dict:
    C = EcommerceCustomer
    rows = (
        await db.execute(
            select(
                C.segment,
                func.count(),
                func.coalesce(func.sum(C.total_spend), 0),
                func.avg(C.recency_days),
                func.avg(C.order_count),
            )
            .where(C.segment.is_not(None))
            .group_by(C.segment)
        )
    ).all()
    by_key = {seg: (int(n), float(spend), recency, orders) for seg, n, spend, recency, orders in rows}
    total_customers = sum(v[0] for v in by_key.values())
    total_revenue = sum(v[1] for v in by_key.values())

    from app.segments.definitions import SEGMENTS  # local import keeps module import order simple

    segments = []
    for definition in SEGMENTS:
        count, spend, recency, orders = by_key.get(definition.key, (0, 0.0, None, None))
        segments.append(
            {
                "key": definition.key,
                "name": definition.name,
                "description": definition.description,
                "action": definition.action,
                "customers": count,
                "share": round(count / total_customers, 4) if total_customers else 0.0,
                "revenue": round(spend, 2),
                "revenue_share": round(spend / total_revenue, 4) if total_revenue else 0.0,
                "avg_spend": round(spend / count, 2) if count else None,
                "avg_recency_days": round(float(recency), 1) if recency is not None else None,
                "avg_orders": round(float(orders), 2) if orders is not None else None,
            }
        )

    grid = (
        await db.execute(
            select(C.r_score, C.f_score, func.count())
            .where(C.r_score.is_not(None), C.f_score.is_not(None))
            .group_by(C.r_score, C.f_score)
        )
    ).all()
    computed_at = (await db.execute(select(func.max(C.profile_computed_at)))).scalar_one()

    return {
        "total_customers": total_customers,
        "profiles_computed_at": _iso(computed_at),
        "segments": segments,
        "rfm_grid": [{"r": int(r), "f": int(f), "count": int(n)} for r, f, n in grid],
    }
