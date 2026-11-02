"""Analytics report: one call that feeds the whole Analytics screen."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Date, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.intelligence import purchase_quantity, purchase_value
from app.database.models.customer import EcommerceCustomer
from app.database.models.event import EventType, UserEvent
from app.database.models.offer import OfferInteraction, OfferRedemption
from app.database.models.product import Product
from app.database.models.recommendation_log import RecommendationLog

FUNNEL_STEPS = (
    ("viewed", "Viewed a product", EventType.PRODUCT_VIEW),
    ("carted", "Added to cart", EventType.ADD_TO_CART),
    ("checkout", "Started checkout", EventType.CHECKOUT_STARTED),
    ("purchased", "Purchased", EventType.PURCHASE),
)


def change(current: float, previous: float | None) -> float | None:
    """Relative change versus the previous period (None when there is nothing to compare to)."""
    if previous is None or previous == 0:
        return None
    return round((current - previous) / previous, 4)


def kpi(current: float, previous: float | None) -> dict:
    return {"value": round(current, 2), "previous": None if previous is None else round(previous, 2), "change": change(current, previous)}


def funnel_rows(counts: list[int]) -> list[dict]:
    """counts: distinct customers per step, in FUNNEL_STEPS order."""
    rows = []
    for index, ((key, label, _), count) in enumerate(zip(FUNNEL_STEPS, counts, strict=True)):
        start, previous = counts[0], counts[index - 1] if index else count
        rows.append(
            {
                "step": key,
                "label": label,
                "customers": count,
                "rate_from_start": round(count / start, 4) if start else None,
                "rate_from_previous": round(count / previous, 4) if previous else None,
            }
        )
    return rows


def _utc_day(moment: datetime) -> date:
    return moment.astimezone(timezone.utc).date()


async def build_report(db: AsyncSession, days: int) -> dict:
    now = datetime.now(timezone.utc)
    start_date = now.date() - timedelta(days=days - 1)
    since = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    prev_since = since - timedelta(days=days)
    dates = [start_date + timedelta(days=i) for i in range(days)]
    day = cast(func.timezone("UTC", UserEvent.occurred_at), Date)
    E = UserEvent

    def count_of(event_type: EventType):
        return func.count().filter(E.event_type == event_type)

    # --- daily event series (current period)
    daily_events = {
        d: row
        for d, *row in (
            await db.execute(
                select(
                    day,
                    func.count(),
                    func.count(distinct(E.external_user_id)),
                    count_of(EventType.RECOMMENDATION_VIEW),
                    count_of(EventType.RECOMMENDATION_CLICK),
                )
                .where(E.occurred_at >= since)
                .group_by(day)
            )
        ).all()
    }

    async def distinct_customers(start: datetime, end: datetime | None = None) -> int:
        query = select(func.count(distinct(E.external_user_id))).where(E.occurred_at >= start)
        if end is not None:
            query = query.where(E.occurred_at < end)
        return int((await db.execute(query)).scalar_one())

    async def events_between(start: datetime, end: datetime) -> int:
        return int((await db.execute(select(func.count()).select_from(E).where(E.occurred_at >= start, E.occurred_at < end))).scalar_one())

    active_now, active_prev = await distinct_customers(since), await distinct_customers(prev_since, since)
    events_prev = await events_between(prev_since, since)

    # --- money: purchases and refunds of both periods, valued in Python (price x quantity / amount)
    revenue = {"cur": defaultdict(float), "prev": defaultdict(float)}
    order_keys: dict[str, dict[date, set]] = {"cur": defaultdict(set), "prev": defaultdict(set)}
    buyers: dict[str, set[str]] = {"cur": set(), "prev": set()}
    product_revenue: dict[str, float] = defaultdict(float)
    product_units: dict[str, int] = defaultdict(int)
    category_revenue: dict[str, float] = defaultdict(float)

    money_rows = await db.execute(
        select(E.external_user_id, E.session_id, E.occurred_at, E.event_type, E.product_id, E.event_metadata, Product.price, Product.category)
        .select_from(E)
        .outerjoin(Product, Product.external_product_id == E.product_id)
        .where(E.event_type.in_([EventType.PURCHASE, EventType.PURCHASE_CANCELLED, EventType.RETURN]), E.occurred_at >= prev_since)
    )
    for uid, session_id, when, event_type, product_id, metadata, price, category in money_rows.all():
        period = "cur" if when >= since else "prev"
        d = _utc_day(when)
        value = purchase_value(metadata, float(price) if price is not None else None)
        if event_type == EventType.PURCHASE:
            revenue[period][d] += value
            order_keys[period][d].add((uid, session_id or d.isoformat()))
            buyers[period].add(uid)
            if period == "cur" and product_id:
                product_revenue[product_id] += value
                product_units[product_id] += purchase_quantity(metadata)
                if category:
                    category_revenue[category] += value
        else:
            revenue[period][d] -= value
            if period == "cur" and product_id:
                product_revenue[product_id] -= value
                if category:
                    category_revenue[category] -= value

    revenue_now, revenue_prev = max(sum(revenue["cur"].values()), 0.0), max(sum(revenue["prev"].values()), 0.0)
    orders_now = sum(len(v) for v in order_keys["cur"].values())
    orders_prev = sum(len(v) for v in order_keys["prev"].values())

    # --- new customers, recommendations, offers per day
    first_seen_day = cast(func.timezone("UTC", EcommerceCustomer.first_seen_at), Date)
    new_by_day = {
        d: int(n)
        for d, n in (
            await db.execute(
                select(first_seen_day, func.count()).where(EcommerceCustomer.first_seen_at >= since).group_by(first_seen_day)
            )
        ).all()
    }
    new_prev = int(
        (
            await db.execute(
                select(func.count()).select_from(EcommerceCustomer).where(
                    EcommerceCustomer.first_seen_at >= prev_since, EcommerceCustomer.first_seen_at < since
                )
            )
        ).scalar_one()
    )

    served_day = cast(func.timezone("UTC", RecommendationLog.created_at), Date)
    served_by_day = {
        d: int(n)
        for d, n in (
            await db.execute(select(served_day, func.count()).where(RecommendationLog.created_at >= since).group_by(served_day))
        ).all()
    }

    inter_day = cast(func.timezone("UTC", OfferInteraction.occurred_at), Date)
    offer_inter: dict[date, dict[str, int]] = defaultdict(dict)
    for d, action, n in (
        await db.execute(
            select(inter_day, OfferInteraction.action, func.count()).where(OfferInteraction.occurred_at >= since).group_by(inter_day, OfferInteraction.action)
        )
    ).all():
        offer_inter[d][action] = int(n)
    red_day = cast(func.timezone("UTC", OfferRedemption.redeemed_at), Date)
    offer_red = {
        d: (int(n), float(disc))
        for d, n, disc in (
            await db.execute(
                select(red_day, func.count(), func.coalesce(func.sum(OfferRedemption.discount_amount), 0))
                .where(OfferRedemption.redeemed_at >= since)
                .group_by(red_day)
            )
        ).all()
    }

    # --- series
    daily = []
    for d in dates:
        events_n, customers_n, rec_views, rec_clicks = daily_events.get(d, (0, 0, 0, 0))
        redeemed, discount = offer_red.get(d, (0, 0.0))
        daily.append(
            {
                "date": d.isoformat(),
                "events": int(events_n),
                "active_customers": int(customers_n),
                "new_customers": new_by_day.get(d, 0),
                "orders": len(order_keys["cur"].get(d, ())),
                "revenue": round(revenue["cur"].get(d, 0.0), 2),
                "rec_views": int(rec_views),
                "rec_clicks": int(rec_clicks),
                "recs_served": served_by_day.get(d, 0),
                "offer_impressions": offer_inter[d].get("impression", 0),
                "offer_clicks": offer_inter[d].get("click", 0),
                "offer_redemptions": redeemed,
                "offer_discount": round(discount, 2),
            }
        )

    # --- funnel (distinct customers per step)
    funnel_counts = (
        await db.execute(select(*[func.count(distinct(E.external_user_id)).filter(E.event_type == step) for _, _, step in FUNNEL_STEPS]).where(E.occurred_at >= since))
    ).one()

    # --- top products (by net revenue), enriched with names and views
    top_ids = [pid for pid, value in sorted(product_revenue.items(), key=lambda kv: (-kv[1], kv[0])) if value > 0][:10]
    names = {
        ext_id: (name, category)
        for ext_id, name, category in (
            await db.execute(select(Product.external_product_id, Product.name, Product.category).where(Product.external_product_id.in_(top_ids)))
        ).all()
    } if top_ids else {}
    views = {
        pid: int(n)
        for pid, n in (
            await db.execute(
                select(E.product_id, func.count())
                .where(E.product_id.in_(top_ids), E.event_type == EventType.PRODUCT_VIEW, E.occurred_at >= since)
                .group_by(E.product_id)
            )
        ).all()
    } if top_ids else {}
    top_products = [
        {
            "product_id": pid,
            "name": names.get(pid, (pid, None))[0],
            "category": names.get(pid, (pid, None))[1],
            "units": product_units.get(pid, 0),
            "revenue": round(product_revenue[pid], 2),
            "views": views.get(pid, 0),
        }
        for pid in top_ids
    ]

    category_total = sum(v for v in category_revenue.values() if v > 0)
    top_categories = [
        {"category": c, "revenue": round(v, 2), "share": round(v / category_total, 4) if category_total else 0.0}
        for c, v in sorted(category_revenue.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
        if v > 0
    ]

    platform_rows = (
        await db.execute(select(E.platform, func.count()).where(E.occurred_at >= since).group_by(E.platform).order_by(func.count().desc()))
    ).all()
    platform_total = sum(int(n) for _, n in platform_rows)
    platforms = [
        {"platform": p.value if hasattr(p, "value") else str(p), "events": int(n), "share": round(int(n) / platform_total, 4) if platform_total else 0.0}
        for p, n in platform_rows
    ]

    events_now = sum(row["events"] for row in daily)
    aov_now = revenue_now / orders_now if orders_now else 0.0
    aov_prev = revenue_prev / orders_prev if orders_prev else None
    conversion_now = len(buyers["cur"]) / active_now if active_now else 0.0
    conversion_prev = len(buyers["prev"]) / active_prev if active_prev else 0.0

    return {
        "days": days,
        "from": start_date.isoformat(),
        "to": now.date().isoformat(),
        "kpis": {
            "revenue": kpi(revenue_now, revenue_prev),
            "orders": kpi(orders_now, orders_prev),
            "avg_order_value": kpi(aov_now, aov_prev),
            "active_customers": kpi(active_now, active_prev),
            "new_customers": kpi(sum(new_by_day.values()), new_prev),
            "conversion_rate": kpi(conversion_now, conversion_prev),
            "events": kpi(events_now, events_prev),
        },
        "daily": daily,
        "funnel": funnel_rows([int(n) for n in funnel_counts]),
        "top_products": top_products,
        "top_categories": top_categories,
        "platforms": platforms,
    }
