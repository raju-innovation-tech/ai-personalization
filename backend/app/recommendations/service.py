"""Loads data for the engine, caches the model snapshot, logs served requests."""
import asyncio
import math
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import Date, String, cast, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.database.models.event import EventType, UserEvent
from app.database.models.product import Product
from app.database.models.recommendation_log import RecommendationLog
from app.recommendations.engine import EVENT_WEIGHTS, ProductInfo, Scored, Snapshot

logger = get_logger(__name__)


def _product_info(row: Product) -> ProductInfo:
    attributes = row.attributes or {}
    return ProductInfo(
        product_id=row.external_product_id,
        name=row.name,
        category=row.category,
        brand=row.brand,
        price=float(row.price) if row.price is not None else None,
        image_url=row.image_url,
        rating=float(row.rating) if row.rating is not None else None,
        in_stock=row.in_stock,
        is_active=row.is_active,
        tags=tuple(str(t) for t in (row.tags or [])),
        color=attributes.get("color") if isinstance(attributes, dict) else None,
    )


async def load_snapshot(db: AsyncSession) -> Snapshot:
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.RECO_LOOKBACK_DAYS)

    products = [_product_info(p) for p in (await db.execute(select(Product))).scalars().all()]

    # Exponential time decay computed in SQL: 1.0 for "now", 0.5 after one half-life.
    age_seconds = func.greatest(extract("epoch", func.now() - UserEvent.occurred_at), 0.0)
    decay = func.exp(-math.log(2) * age_seconds / (86400.0 * settings.RECO_HALF_LIFE_DAYS))
    weighted_types = [EventType[name] for name in EVENT_WEIGHTS if name in EventType.__members__]

    interaction_rows = (
        await db.execute(
            select(
                UserEvent.external_user_id,
                UserEvent.product_id,
                UserEvent.event_type,
                func.sum(decay),
            )
            .where(
                UserEvent.product_id.is_not(None),
                UserEvent.occurred_at >= cutoff,
                UserEvent.event_type.in_(weighted_types),
            )
            .group_by(UserEvent.external_user_id, UserEvent.product_id, UserEvent.event_type)
        )
    ).all()
    interactions = [(u, p, et.name, float(d or 0.0)) for u, p, et, d in interaction_rows]

    session_key = func.coalesce(UserEvent.session_id, cast(cast(UserEvent.occurred_at, Date), String))
    basket_rows = (
        await db.execute(
            select(UserEvent.external_user_id, session_key, UserEvent.product_id)
            .where(
                UserEvent.event_type == EventType.PURCHASE,
                UserEvent.product_id.is_not(None),
                UserEvent.occurred_at >= cutoff,
            )
            .distinct()
        )
    ).all()
    baskets = [(u, s, p) for u, s, p in basket_rows]

    started = time.perf_counter()
    snapshot = await asyncio.to_thread(
        lambda: Snapshot.build(
            products,
            interactions,
            baskets,
            exclude_out_of_stock=settings.RECO_EXCLUDE_OUT_OF_STOCK,
            fbt_min_support=settings.RECO_FBT_MIN_SUPPORT,
        )
    )
    logger.info(
        "reco_snapshot_built",
        products=len(snapshot.products),
        users=len(snapshot.user_items),
        interactions=snapshot.interaction_count,
        fbt_pairs=snapshot.fbt_pair_count,
        build_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return snapshot


class SnapshotCache:
    """In-process cache; rebuilt after the TTL, on demand, or when the catalog changes."""

    def __init__(self) -> None:
        self._snapshot: Snapshot | None = None
        self._built_at = 0.0
        self._locks: dict[int, asyncio.Lock] = {}

    def invalidate(self) -> None:
        self._snapshot = None

    def peek(self) -> Snapshot | None:
        return self._snapshot

    def _fresh(self) -> bool:
        return (
            self._snapshot is not None
            and time.monotonic() - self._built_at < settings.RECO_SNAPSHOT_TTL_SECONDS
        )

    async def get(self, db: AsyncSession, *, force: bool = False) -> Snapshot:
        if not force and self._fresh():
            return self._snapshot  # type: ignore[return-value]
        lock = self._locks.setdefault(id(asyncio.get_running_loop()), asyncio.Lock())
        async with lock:
            if not force and self._fresh():
                return self._snapshot  # type: ignore[return-value]
            snapshot = await load_snapshot(db)
            self._snapshot = snapshot
            self._built_at = time.monotonic()
            return snapshot


snapshot_cache = SnapshotCache()


def reset_snapshot_cache() -> None:
    snapshot_cache.invalidate()


def item_out(snapshot: Snapshot, scored: Scored) -> dict:
    product = snapshot.products[scored.product_id]
    return {
        "product_id": product.product_id,
        "name": product.name,
        "category": product.category,
        "brand": product.brand,
        "price": product.price,
        "image_url": product.image_url,
        "rating": product.rating,
        "in_stock": product.in_stock,
        "score": scored.score,
        "reason": scored.reason,
        "algorithm": scored.algorithm,
    }


async def log_served(
    db: AsyncSession,
    *,
    algorithm: str,
    result_count: int,
    started: float,
    external_user_id: str | None = None,
    product_id: str | None = None,
) -> None:
    """Never let analytics logging break the actual recommendation response."""
    try:
        db.add(
            RecommendationLog(
                algorithm=algorithm,
                external_user_id=external_user_id,
                product_id=product_id,
                result_count=result_count,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("reco_log_failed", error=str(exc))
