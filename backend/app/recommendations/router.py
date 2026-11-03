import time
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_roles, verify_storefront_auth
from app.core.config import settings
from app.core.responses import NotFoundError, success_response
from app.database.database import get_db
from app.database.models.event import EventType, Platform
from app.database.models.recommendation_log import RecommendationLog
from app.database.models.user import User, UserRole
from app.events import service as events_service
from app.experiments import service as experiments_service
from app.events.schemas import EventIn
from app.recommendations import service
from app.recommendations.engine import Snapshot
from app.recommendations.schemas import TrackIn

router = APIRouter(prefix="/recommendations", tags=["Recommendations"], dependencies=[Depends(verify_storefront_auth)])

Limit = Annotated[int, Query(ge=1, le=settings.RECO_MAX_LIMIT, description="Number of items to return")]


def _payload(snapshot: Snapshot, algorithm: str, scored: list, **extra) -> dict:
    return {
        "algorithm": algorithm,
        "count": len(scored),
        "generated_at": snapshot.built_at.isoformat(),
        "items": [service.item_out(snapshot, s) for s in scored],
        **extra,
    }


def _require_product(snapshot: Snapshot, product_id: str) -> None:
    if product_id not in snapshot.products:
        raise NotFoundError(f"Product '{product_id}' is not in the catalog", code="PRODUCT_NOT_FOUND")


@router.get("/popular", summary="Trending / most popular products")
async def popular(
    limit: Limit = 10,
    category: str | None = Query(default=None, max_length=255),
    db: AsyncSession = Depends(get_db),
):
    started = time.perf_counter()
    snapshot = await service.snapshot_cache.get(db)
    items = snapshot.popular(limit, category=category)
    await service.log_served(db, algorithm="popular", result_count=len(items), started=started)
    return success_response(_payload(snapshot, "popular", items, category=category))


@router.get("/similar/{product_id}", summary="Products similar to a given product")
async def similar(product_id: str, limit: Limit = 10, db: AsyncSession = Depends(get_db)):
    started = time.perf_counter()
    snapshot = await service.snapshot_cache.get(db)
    _require_product(snapshot, product_id)
    items = snapshot.similar(product_id, limit)
    await service.log_served(
        db, algorithm="similar", result_count=len(items), started=started, product_id=product_id
    )
    return success_response(_payload(snapshot, "similar", items, product_id=product_id))


@router.get("/frequently-bought/{product_id}", summary="Frequently bought together")
async def frequently_bought(product_id: str, limit: Limit = 10, db: AsyncSession = Depends(get_db)):
    started = time.perf_counter()
    snapshot = await service.snapshot_cache.get(db)
    _require_product(snapshot, product_id)
    items = snapshot.frequently_bought_together(product_id, limit)
    await service.log_served(
        db, algorithm="fbt", result_count=len(items), started=started, product_id=product_id
    )
    return success_response(_payload(snapshot, "fbt", items, product_id=product_id))


@router.get("/user/{external_user_id}", summary="Personalised recommendations for a customer")
async def for_user(external_user_id: str, limit: Limit = 10, db: AsyncSession = Depends(get_db)):
    started = time.perf_counter()
    snapshot = await service.snapshot_cache.get(db)
    # A/B test: a running "recommendations" experiment may switch this customer to another strategy.
    assignment = await experiments_service.assign_for_request(db, "recommendations", external_user_id)
    strategy = assignment.config.get("strategy", "hybrid") if assignment else "hybrid"
    items, algorithm = snapshot.for_user(external_user_id, limit, strategy)
    await service.log_served(
        db,
        algorithm=algorithm,
        result_count=len(items),
        started=started,
        external_user_id=external_user_id,
    )
    return success_response(
        _payload(
            snapshot,
            algorithm,
            items,
            external_user_id=external_user_id,
            personalized=algorithm != "popular",
            experiment=assignment.public() if assignment else None,
        )
    )


@router.get("/home/{external_user_id}", summary="Home-page feed: several recommendation rows")
async def home_feed(external_user_id: str, limit: Limit = 10, db: AsyncSession = Depends(get_db)):
    started = time.perf_counter()
    snapshot = await service.snapshot_cache.get(db)
    purchased = snapshot.user_purchased.get(external_user_id, set())

    personal, algorithm = snapshot.for_user(external_user_id, limit)
    taken = {s.product_id for s in personal} | purchased
    sections = [
        {
            "key": "for_you",
            "title": "Recommended for you" if algorithm == "hybrid" else "Popular right now",
            "algorithm": algorithm,
            "items": [service.item_out(snapshot, s) for s in personal],
        }
    ]

    if algorithm == "hybrid":
        trending = snapshot.popular(limit, exclude=taken)
        sections.append(
            {
                "key": "trending",
                "title": "Trending now",
                "algorithm": "popular",
                "items": [service.item_out(snapshot, s) for s in trending],
            }
        )
        category = snapshot.top_category(external_user_id)
        if category:
            taken |= {s.product_id for s in trending}
            in_category = snapshot.popular(
                limit, category=category, exclude=taken, reason=f"Popular in {category}"
            )
            if in_category:
                sections.append(
                    {
                        "key": "top_category",
                        "title": f"Popular in {category}",
                        "algorithm": "popular",
                        "items": [service.item_out(snapshot, s) for s in in_category],
                    }
                )

    await service.log_served(
        db,
        algorithm="home",
        result_count=sum(len(s["items"]) for s in sections),
        started=started,
        external_user_id=external_user_id,
    )
    return success_response(
        {
            "external_user_id": external_user_id,
            "personalized": algorithm == "hybrid",
            "generated_at": snapshot.built_at.isoformat(),
            "sections": sections,
        }
    )


@router.post("/track", status_code=201, summary="Track a recommendation impression or click")
async def track(payload: TrackIn, db: AsyncSession = Depends(get_db)):
    """Stored as a RECOMMENDATION_VIEW / RECOMMENDATION_CLICK event (feeds CTR + the models)."""
    event = EventIn(
        event_type=EventType.RECOMMENDATION_CLICK if payload.action == "click" else EventType.RECOMMENDATION_VIEW,
        external_user_id=payload.external_user_id,
        product_id=payload.product_id,
        session_id=payload.session_id,
        platform=Platform.UNKNOWN,
        timestamp=payload.timestamp or datetime.now(timezone.utc),
        metadata={"algorithm": payload.algorithm, "source": "recommendations.track"},
        idempotency_key=payload.idempotency_key,
    )
    key, duplicate = await events_service.ingest_single_event(db, event)
    return success_response(
        {"idempotency_key": key, "status": "duplicate" if duplicate else "accepted"}
    )


@router.get("/status", summary="Engine status and usage (admin dashboard)")
async def status(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    snapshot = await service.snapshot_cache.get(db)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    async def usage(since: datetime | None) -> dict[str, int]:
        query = select(RecommendationLog.algorithm, func.count()).group_by(RecommendationLog.algorithm)
        if since is not None:
            query = query.where(RecommendationLog.created_at >= since)
        return {algo: int(n) for algo, n in (await db.execute(query)).all()}

    total, last_7d = await usage(None), await usage(week_ago)
    return success_response(
        {
            "built_at": snapshot.built_at.isoformat(),
            "ttl_seconds": settings.RECO_SNAPSHOT_TTL_SECONDS,
            "lookback_days": settings.RECO_LOOKBACK_DAYS,
            "half_life_days": settings.RECO_HALF_LIFE_DAYS,
            "products": len(snapshot.products),
            "customers_with_history": len(snapshot.user_items),
            "interactions": snapshot.interaction_count,
            "baskets": snapshot.basket_count,
            "fbt_pairs": snapshot.fbt_pair_count,
            "served_total": sum(total.values()),
            "served_7d": sum(last_7d.values()),
            "served_by_algorithm": {
                algo: {"total": total.get(algo, 0), "last_7d": last_7d.get(algo, 0)} for algo in sorted(total)
            },
        }
    )


@router.post("/refresh", summary="Rebuild the model snapshot now (admin)")
async def refresh(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)),
):
    snapshot = await service.snapshot_cache.get(db, force=True)
    return success_response(
        {
            "built_at": snapshot.built_at.isoformat(),
            "products": len(snapshot.products),
            "customers_with_history": len(snapshot.user_items),
            "interactions": snapshot.interaction_count,
        }
    )
