from datetime import datetime, timedelta, timezone

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.report import build_report
from app.auth.dependencies import get_current_user
from app.core.responses import success_response
from app.database.database import get_db
from app.database.models.customer import EcommerceCustomer
from app.database.models.event import EventType, UserEvent
from app.database.models.product import Product
from app.database.models.recommendation_log import RecommendationLog
from app.database.models.user import User
from app.offers import service as offers_service

router = APIRouter(prefix="/analytics", tags=["Analytics"])

DAYS = 14


@router.get("/overview", summary="Numbers for the admin dashboard")
async def overview(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    since_7d, since_30d = now - timedelta(days=7), now - timedelta(days=30)
    since_chart = datetime.combine(now.date() - timedelta(days=DAYS - 1), datetime.min.time(), tzinfo=timezone.utc)

    async def scalar(query):
        return int((await db.execute(query)).scalar_one() or 0)

    customers = await scalar(select(func.count()).select_from(EcommerceCustomer))
    products = await scalar(select(func.count()).select_from(Product))
    active_products = await scalar(select(func.count()).select_from(Product).where(Product.is_active.is_(True)))
    events_total = await scalar(select(func.count()).select_from(UserEvent))
    events_7d = await scalar(select(func.count()).select_from(UserEvent).where(UserEvent.occurred_at >= since_7d))
    purchases_30d = await scalar(
        select(func.count()).select_from(UserEvent).where(
            UserEvent.event_type == EventType.PURCHASE, UserEvent.occurred_at >= since_30d
        )
    )
    served_total = await scalar(select(func.count()).select_from(RecommendationLog))
    served_7d = await scalar(
        select(func.count()).select_from(RecommendationLog).where(RecommendationLog.created_at >= since_7d)
    )

    # Recommendation click-through rate over the last 30 days (from tracked events).
    views = await scalar(
        select(func.count()).select_from(UserEvent).where(
            UserEvent.event_type == EventType.RECOMMENDATION_VIEW, UserEvent.occurred_at >= since_30d
        )
    )
    clicks = await scalar(
        select(func.count()).select_from(UserEvent).where(
            UserEvent.event_type == EventType.RECOMMENDATION_CLICK, UserEvent.occurred_at >= since_30d
        )
    )

    day = cast(func.timezone("UTC", UserEvent.occurred_at), Date)
    per_day = {
        d: int(n)
        for d, n in (
            await db.execute(
                select(day, func.count()).where(UserEvent.occurred_at >= since_chart).group_by(day)
            )
        ).all()
    }
    start = since_chart.date()
    events_by_day = [
        {"date": (d := start + timedelta(days=i)).isoformat(), "count": per_day.get(d, 0)} for i in range(DAYS)
    ]

    by_type = (
        await db.execute(
            select(UserEvent.event_type, func.count().label("n"))
            .where(UserEvent.occurred_at >= since_30d)
            .group_by(UserEvent.event_type)
            .order_by(func.count().desc())
            .limit(8)
        )
    ).all()

    top_categories = (
        await db.execute(
            select(Product.category, func.count().label("n"))
            .join(UserEvent, UserEvent.product_id == Product.external_product_id)
            .where(UserEvent.occurred_at >= since_30d, Product.category.is_not(None))
            .group_by(Product.category)
            .order_by(func.count().desc())
            .limit(5)
        )
    ).all()

    offer_totals = await offers_service.totals(db)

    return success_response(
        {
            "totals": {
                "customers": customers,
                "products": products,
                "active_products": active_products,
                "events": events_total,
                "events_7d": events_7d,
                "purchases_30d": purchases_30d,
                "recommendations_served": served_total,
                "recommendations_served_7d": served_7d,
            },
            "offers": {
                "active": offer_totals["active_now"],
                "impressions": offer_totals["all_time"]["impressions"],
                "clicks": offer_totals["all_time"]["clicks"],
                "redemptions": offer_totals["all_time"]["redemptions"],
                "discount_given": offer_totals["all_time"]["discount_given"],
            },
            "recommendation_ctr_30d": {
                "impressions": views,
                "clicks": clicks,
                "ctr": round(clicks / views, 4) if views else None,
            },
            "events_by_day": events_by_day,
            "events_by_type": [{"event_type": t.name, "count": int(n)} for t, n in by_type],
            "top_categories": [{"category": c, "interactions": int(n)} for c, n in top_categories],
        }
    )


@router.get("/report", summary="Analytics report for the last N days, compared with the N days before")
async def report(
    days: Annotated[int, Query(ge=1, le=365, description="Length of the period in days")] = 30,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return success_response(await build_report(db, days))
