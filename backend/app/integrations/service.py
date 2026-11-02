"""Integration status: is the shop actually sending good data?"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.models.customer import EcommerceCustomer
from app.database.models.event import EventType, UserEvent
from app.database.models.offer import OfferRedemption
from app.database.models.product import Product
from app.database.models.recommendation_log import RecommendationLog
from app.database.models.user import User, UserRole

CHECKOUT_ROLES = (UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.MARKETING_MANAGER)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def build_checklist(d: dict) -> list[dict]:
    """Turns the raw numbers into a to-do list. Pure function (unit tested)."""

    def item(key: str, title: str, status: str, detail: str) -> dict:
        return {"key": key, "title": title, "status": status, "detail": detail}

    events, quality, catalog = d["events"], d["data_quality"], d["catalog"]
    items = [
        item(
            "catalog",
            "Product catalog synced",
            "ok" if catalog["products"] > 0 else "todo",
            f"{catalog['products']} products" if catalog["products"] else "Push your catalog with POST /products/bulk.",
        )
    ]
    if events["total"] == 0:
        items.append(item("events", "Behaviour events arriving", "todo", "No events yet. Send them with POST /events/batch."))
    elif events["last_24h"] == 0:
        items.append(item("events", "Behaviour events arriving", "warning", "Events exist, but none in the last 24 hours - is the integration still running?"))
    else:
        items.append(item("events", "Behaviour events arriving", "ok", f"{events['last_24h']} events in the last 24 hours"))

    items.append(
        item(
            "purchases",
            "Purchases tracked",
            "ok" if quality["purchase_events_30d"] > 0 else "todo",
            f"{quality['purchase_events_30d']} purchase events in 30 days" if quality["purchase_events_30d"] else "Send PURCHASE events so revenue, RFM and segments work.",
        )
    )
    unknown_rate = quality["unknown_product_rate"]
    items.append(
        item(
            "product_ids",
            "Event product ids match the catalog",
            "ok" if unknown_rate is None or unknown_rate <= 0.05 else "warning",
            "No product events yet" if unknown_rate is None else f"{unknown_rate:.1%} of product events reference an unknown product id",
        )
    )
    no_session = quality["purchases_without_session_rate"]
    items.append(
        item(
            "sessions",
            "Purchases carry a session_id",
            "ok" if no_session is None or no_session <= 0.10 else "warning",
            "No purchases yet"
            if no_session is None
            else (f"{no_session:.1%} of purchases have no session_id - orders are then grouped per day, not per order" if no_session > 0.10 else "Orders are grouped correctly"),
        )
    )
    items.append(
        item(
            "profiles",
            "Customer segments computed",
            "ok" if d["profiles"]["last_computed_at"] else "todo",
            "Profiles are up to date" if d["profiles"]["last_computed_at"] else "Press Recompute on the Segments page (it also runs automatically).",
        )
    )
    items.append(
        item(
            "recommendations",
            "Recommendations served to the storefront",
            "ok" if d["recommendations"]["served_total"] > 0 else "todo",
            f"{d['recommendations']['served_total']} requests served" if d["recommendations"]["served_total"] else "Call GET /recommendations/user/{id} from your site.",
        )
    )
    items.append(
        item(
            "checkout",
            "Offers redeemed at checkout",
            "ok" if d["checkout"]["redemptions_total"] > 0 else "todo",
            f"{d['checkout']['redemptions_total']} redemptions" if d["checkout"]["redemptions_total"] else "Optional: call /offers/validate and /offers/redeem when an order is placed.",
        )
    )
    items.append(
        item(
            "service_account",
            "A dedicated service account for your shop",
            "ok" if d["accounts_summary"]["checkout_capable"] >= 2 else "warning",
            "Separate accounts exist" if d["accounts_summary"]["checkout_capable"] >= 2 else "Only one account can call the checkout API - create a service account (Users page).",
        )
    )
    return items


async def collect(db: AsyncSession, *, include_accounts: bool) -> dict:
    now = datetime.now(timezone.utc)
    since_24h, since_7d, since_30d = now - timedelta(hours=24), now - timedelta(days=7), now - timedelta(days=30)
    E = UserEvent

    async def scalar(query):
        return (await db.execute(query)).scalar_one()

    total = int(await scalar(select(func.count()).select_from(E)))
    last_event = await scalar(select(func.max(E.occurred_at)))
    events = {
        "total": total,
        "last_24h": int(await scalar(select(func.count()).select_from(E).where(E.occurred_at >= since_24h))),
        "last_7d": int(await scalar(select(func.count()).select_from(E).where(E.occurred_at >= since_7d))),
        "last_event_at": _iso(last_event),
        "event_types_30d": int(await scalar(select(func.count(func.distinct(E.event_type))).where(E.occurred_at >= since_30d))),
    }

    products = int(await scalar(select(func.count()).select_from(Product)))
    catalog = {
        "products": products,
        "active": int(await scalar(select(func.count()).select_from(Product).where(Product.is_active.is_(True)))),
        "out_of_stock": int(await scalar(select(func.count()).select_from(Product).where(Product.in_stock.is_(False)))),
        "last_updated_at": _iso(await scalar(select(func.max(Product.updated_at)))),
    }

    with_product = int(await scalar(select(func.count()).select_from(E).where(E.product_id.is_not(None), E.occurred_at >= since_30d)))
    unknown = int(
        await scalar(
            select(func.count()).select_from(E).where(
                E.product_id.is_not(None), E.occurred_at >= since_30d, ~exists().where(Product.external_product_id == E.product_id)
            )
        )
    )
    purchases = int(await scalar(select(func.count()).select_from(E).where(E.event_type == EventType.PURCHASE, E.occurred_at >= since_30d)))
    purchases_no_session = int(
        await scalar(
            select(func.count()).select_from(E).where(E.event_type == EventType.PURCHASE, E.occurred_at >= since_30d, E.session_id.is_(None))
        )
    )
    data_quality = {
        "product_events_30d": with_product,
        "unknown_product_events_30d": unknown,
        "unknown_product_rate": round(unknown / with_product, 4) if with_product else None,
        "purchase_events_30d": purchases,
        "purchases_without_session_30d": purchases_no_session,
        "purchases_without_session_rate": round(purchases_no_session / purchases, 4) if purchases else None,
    }

    users = (await db.execute(select(User).order_by(User.created_at, User.email))).scalars().all()
    accounts_summary = {
        "active": sum(1 for u in users if u.is_active),
        "checkout_capable": sum(1 for u in users if u.is_active and u.role in CHECKOUT_ROLES),
    }

    data = {
        "events": events,
        "catalog": catalog,
        "data_quality": data_quality,
        "profiles": {"last_computed_at": _iso(await scalar(select(func.max(EcommerceCustomer.profile_computed_at))))},
        "recommendations": {
            "served_total": int(await scalar(select(func.count()).select_from(RecommendationLog))),
            "last_served_at": _iso(await scalar(select(func.max(RecommendationLog.created_at)))),
        },
        "checkout": {
            "redemptions_total": int(await scalar(select(func.count()).select_from(OfferRedemption))),
            "last_redemption_at": _iso(await scalar(select(func.max(OfferRedemption.redeemed_at)))),
        },
        "accounts_summary": accounts_summary,
    }
    checklist = build_checklist(data)
    done = sum(1 for c in checklist if c["status"] == "ok")
    return {
        "api": {"base_path": settings.API_V1_PREFIX, "docs_path": "/docs"},
        **data,
        "accounts": [
            {"email": u.email, "full_name": u.full_name, "role": u.role.value, "is_active": u.is_active} for u in users
        ]
        if include_accounts
        else None,
        "checklist": checklist,
        "score": round(done / len(checklist), 4),
    }
