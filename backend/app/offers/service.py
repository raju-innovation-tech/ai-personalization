"""Database side of the offer engine."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.responses import ApiError
from app.database.models.customer import EcommerceCustomer
from app.database.models.event import EventType, Platform
from app.database.models.offer import Offer, OfferInteraction, OfferRedemption
from app.events import service as events_service
from app.events.schemas import EventIn
from app.offers import engine
from app.offers.engine import Context, OfferRule, Usage
from app.offers.schemas import OfferIn
from app.segments.definitions import SEGMENT_BY_KEY

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active", "ended"},
    "active": {"paused", "ended"},
    "paused": {"active", "ended"},
    "ended": set(),
}


# ------------------------------------------------------------------ conversion
def to_rule(offer: Offer) -> OfferRule:
    return OfferRule(
        id=str(offer.id),
        code=offer.code,
        name=offer.name,
        description=offer.description,
        offer_type=offer.offer_type,
        value=float(offer.value),
        status=offer.status,
        max_discount=float(offer.max_discount) if offer.max_discount is not None else None,
        min_order_value=float(offer.min_order_value) if offer.min_order_value is not None else None,
        max_redemptions=offer.max_redemptions,
        max_per_customer=offer.max_per_customer,
        starts_at=offer.starts_at,
        ends_at=offer.ends_at,
        target_segments=tuple(offer.target_segments or ()),
        target_categories=tuple(offer.target_categories or ()),
        priority=offer.priority,
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def offer_out(offer: Offer, stats: dict | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    stats = stats or {}
    redemptions = stats.get("redemptions", 0)
    impressions = stats.get("impressions", 0)
    clicks = stats.get("clicks", 0)
    return {
        "id": str(offer.id),
        "code": offer.code,
        "name": offer.name,
        "description": offer.description,
        "offer_type": offer.offer_type,
        "value": float(offer.value),
        "max_discount": float(offer.max_discount) if offer.max_discount is not None else None,
        "min_order_value": float(offer.min_order_value) if offer.min_order_value is not None else None,
        "max_redemptions": offer.max_redemptions,
        "max_per_customer": offer.max_per_customer,
        "status": offer.status,
        "effective_status": engine.effective_status(to_rule(offer), now),
        "starts_at": _iso(offer.starts_at),
        "ends_at": _iso(offer.ends_at),
        "target_segments": list(offer.target_segments or []),
        "target_categories": list(offer.target_categories or []),
        "priority": offer.priority,
        "created_by": offer.created_by,
        "created_at": _iso(offer.created_at),
        "updated_at": _iso(offer.updated_at),
        "stats": {
            "impressions": impressions,
            "clicks": clicks,
            "redemptions": redemptions,
            "ctr": round(clicks / impressions, 4) if impressions else None,
            "redemption_rate": round(redemptions / impressions, 4) if impressions else None,
            "discount_given": stats.get("discount_given", 0.0),
            "revenue": stats.get("revenue", 0.0),
            "remaining": (max(offer.max_redemptions - redemptions, 0) if offer.max_redemptions is not None else None),
        },
    }


def public_offer_out(ranked: engine.Ranked) -> dict:
    o = ranked.offer
    return {
        "id": o.id,
        "code": o.code,
        "name": o.name,
        "description": o.description,
        "offer_type": o.offer_type,
        "value": o.value,
        "max_discount": o.max_discount,
        "min_order_value": o.min_order_value,
        "ends_at": _iso(o.ends_at),
        "score": ranked.score,
        "reason": ranked.reason,
        "discount_preview": ranked.discount_preview,
        "free_shipping": ranked.free_shipping,
    }


# --------------------------------------------------------------------- queries
async def get_offer(db: AsyncSession, offer_id: uuid.UUID) -> Offer | None:
    return (await db.execute(select(Offer).where(Offer.id == offer_id))).scalar_one_or_none()


async def get_offer_by_code(db: AsyncSession, code: str, *, lock: bool = False) -> Offer | None:
    query = select(Offer).where(Offer.code == code.strip().upper())
    if lock:
        query = query.with_for_update()  # serialises concurrent redemptions of one offer
    return (await db.execute(query)).scalar_one_or_none()


async def stats_for(db: AsyncSession, offer_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    result: dict[uuid.UUID, dict] = {oid: {} for oid in offer_ids}
    if not offer_ids:
        return result
    for offer_id, action, n in (
        await db.execute(
            select(OfferInteraction.offer_id, OfferInteraction.action, func.count())
            .where(OfferInteraction.offer_id.in_(offer_ids))
            .group_by(OfferInteraction.offer_id, OfferInteraction.action)
        )
    ).all():
        result[offer_id]["impressions" if action == "impression" else "clicks"] = int(n)
    for offer_id, n, discount, revenue in (
        await db.execute(
            select(
                OfferRedemption.offer_id,
                func.count(),
                func.coalesce(func.sum(OfferRedemption.discount_amount), 0),
                func.coalesce(func.sum(OfferRedemption.order_value), 0),
            )
            .where(OfferRedemption.offer_id.in_(offer_ids))
            .group_by(OfferRedemption.offer_id)
        )
    ).all():
        result[offer_id].update(redemptions=int(n), discount_given=round(float(discount), 2), revenue=round(float(revenue), 2))
    return result


async def load_usage(db: AsyncSession, offer_ids: list[uuid.UUID], user_id: str | None) -> dict[uuid.UUID, Usage]:
    totals = {oid: 0 for oid in offer_ids}
    mine = {oid: 0 for oid in offer_ids}
    shown = {oid: 0 for oid in offer_ids}
    if offer_ids:
        for oid, n in (
            await db.execute(
                select(OfferRedemption.offer_id, func.count())
                .where(OfferRedemption.offer_id.in_(offer_ids))
                .group_by(OfferRedemption.offer_id)
            )
        ).all():
            totals[oid] = int(n)
        if user_id:
            for oid, n in (
                await db.execute(
                    select(OfferRedemption.offer_id, func.count())
                    .where(OfferRedemption.offer_id.in_(offer_ids), OfferRedemption.external_user_id == user_id)
                    .group_by(OfferRedemption.offer_id)
                )
            ).all():
                mine[oid] = int(n)
        for oid, n in (
            await db.execute(
                select(OfferInteraction.offer_id, func.count())
                .where(OfferInteraction.offer_id.in_(offer_ids), OfferInteraction.action == "impression")
                .group_by(OfferInteraction.offer_id)
            )
        ).all():
            shown[oid] = int(n)
    return {oid: Usage(totals[oid], mine[oid], shown[oid]) for oid in offer_ids}


async def customer_context(db: AsyncSession, user_id: str, **extra) -> Context:
    row = (
        await db.execute(
            select(EcommerceCustomer.segment, EcommerceCustomer.favorite_category).where(
                EcommerceCustomer.external_user_id == user_id
            )
        )
    ).first()
    segment, favorite = (row[0], row[1]) if row else (None, None)
    definition = SEGMENT_BY_KEY.get(segment) if segment else None
    return Context(
        segment=segment,
        segment_name=definition.name if definition else None,
        favorite_category=favorite,
        **extra,
    )


async def offers_for_user(
    db: AsyncSession,
    user_id: str,
    *,
    limit: int,
    browsing_category: str | None,
    order_value: float | None,
    allowed_codes: set[str] | None = None,
) -> list[engine.Ranked]:
    """allowed_codes (A/B tests): only these offers may be shown; an empty set shows nothing (holdout)."""
    rows = (await db.execute(select(Offer).where(Offer.status == "active"))).scalars().all()
    if allowed_codes is not None:
        rows = [r for r in rows if r.code in allowed_codes]
    if not rows:
        return []
    usage = await load_usage(db, [r.id for r in rows], user_id)
    ctx = await customer_context(db, user_id, browsing_category=browsing_category, order_value=order_value)
    candidates = [(to_rule(r), usage[r.id]) for r in rows]
    return engine.rank_offers(candidates, ctx, datetime.now(timezone.utc), limit)


# ------------------------------------------------------------------- admin CRUD
async def list_offers(
    db: AsyncSession, *, status: str | None, q: str | None, sort: str, page: int, page_size: int
) -> tuple[list[Offer], int]:
    def filtered(query):
        if status:
            query = query.where(Offer.status == status)
        if q:
            like = f"%{q.strip()}%"
            query = query.where(Offer.name.ilike(like) | Offer.code.ilike(like))
        return query

    total = (await db.execute(filtered(select(func.count()).select_from(Offer)))).scalar_one()
    order = {
        "created": Offer.created_at.desc(),
        "name": Offer.name.asc(),
        "priority": Offer.priority.desc(),
        "ends": Offer.ends_at.asc().nulls_last(),
    }[sort]
    rows = (
        await db.execute(filtered(select(Offer)).order_by(order, Offer.code).offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return list(rows), int(total)


def _apply(offer: Offer, payload: OfferIn) -> None:
    offer.name = payload.name
    offer.description = payload.description
    offer.offer_type = payload.offer_type
    offer.value = payload.value
    offer.max_discount = payload.max_discount
    offer.min_order_value = payload.min_order_value
    offer.max_redemptions = payload.max_redemptions
    offer.max_per_customer = payload.max_per_customer
    offer.starts_at = payload.starts_at
    offer.ends_at = payload.ends_at
    offer.target_segments = payload.target_segments
    offer.target_categories = payload.target_categories
    offer.priority = payload.priority


async def create_offer(db: AsyncSession, payload: OfferIn, created_by: str) -> Offer:
    if await get_offer_by_code(db, payload.code) is not None:
        raise ApiError("CODE_ALREADY_EXISTS", f"An offer with code '{payload.code}' already exists", status_code=409)
    offer = Offer(code=payload.code, status="draft", created_by=created_by)
    _apply(offer, payload)
    db.add(offer)
    await db.commit()
    await db.refresh(offer)
    return offer


async def update_offer(db: AsyncSession, offer: Offer, payload: OfferIn) -> Offer:
    if payload.code != offer.code:
        raise ApiError("CODE_IMMUTABLE", "The offer code cannot be changed after creation", status_code=422)
    if offer.status == "ended":
        raise ApiError("OFFER_ENDED", "An ended offer cannot be edited", status_code=409)
    _apply(offer, payload)
    await db.commit()
    await db.refresh(offer)
    return offer


async def change_status(db: AsyncSession, offer: Offer, new_status: str) -> Offer:
    if new_status == offer.status:
        return offer
    if new_status not in ALLOWED_TRANSITIONS[offer.status]:
        raise ApiError(
            "INVALID_TRANSITION",
            f"Cannot change an offer from '{offer.status}' to '{new_status}'",
            status_code=409,
        )
    if new_status == "active" and offer.ends_at is not None and offer.ends_at <= datetime.now(timezone.utc):
        raise ApiError("OFFER_ALREADY_EXPIRED", "ends_at is in the past - edit the dates before activating", status_code=422)
    offer.status = new_status
    await db.commit()
    await db.refresh(offer)
    return offer


# ----------------------------------------------------- tracking / validate / redeem
def _hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


async def track(
    db: AsyncSession, offer: Offer, *, user_id: str, action: str, idempotency_key: str | None, when: datetime
) -> bool:
    """Returns True when stored, False for a duplicate idempotency key."""
    result = await db.execute(
        pg_insert(OfferInteraction)
        .values(
            id=uuid.uuid4(),
            offer_id=offer.id,
            external_user_id=user_id,
            action=action,
            occurred_at=when,
            idempotency_key=idempotency_key,
        )
        .on_conflict_do_nothing(index_elements=[OfferInteraction.idempotency_key])
        .returning(OfferInteraction.id)
    )
    stored = result.first() is not None
    if stored:
        await events_service.ingest_events(
            db,
            [
                EventIn(
                    event_type=EventType.OFFER_VIEW if action == "impression" else EventType.OFFER_CLICK,
                    external_user_id=user_id,
                    timestamp=when,
                    platform=Platform.UNKNOWN,
                    metadata={"offer_code": offer.code, "offer_id": str(offer.id), "source": "offers.track"},
                    idempotency_key=_hash("offer-track", str(offer.id), user_id, action, when.isoformat(), idempotency_key or uuid.uuid4().hex),
                )
            ],
        )
    await db.commit()
    return stored


async def check(
    db: AsyncSession, offer: Offer | None, *, user_id: str, order_value: float, categories: list[str]
) -> dict:
    """Validation result for checkout (never raises for business reasons)."""
    if offer is None:
        return {"valid": False, "reason_code": "OFFER_NOT_FOUND", "reason": engine.REASON_MESSAGES["OFFER_NOT_FOUND"]}
    usage = (await load_usage(db, [offer.id], user_id))[offer.id]
    ctx = await customer_context(db, user_id, order_value=order_value, categories=tuple(categories), checkout=True)
    rule = to_rule(offer)
    reason = engine.check_eligibility(rule, usage, ctx, datetime.now(timezone.utc))
    if reason is not None:
        return {"valid": False, "reason_code": reason, "reason": engine.REASON_MESSAGES[reason], "offer_id": str(offer.id)}
    discount, free_shipping = engine.compute_discount(rule, order_value)
    return {
        "valid": True,
        "reason_code": None,
        "reason": None,
        "offer_id": str(offer.id),
        "code": offer.code,
        "name": offer.name,
        "offer_type": offer.offer_type,
        "discount_amount": discount,
        "free_shipping": free_shipping,
        "final_value": round(max(order_value - discount, 0.0), 2),
    }


async def redeem(
    db: AsyncSession, *, code: str, user_id: str, order_ref: str, order_value: float, categories: list[str]
) -> dict:
    """
    Atomically redeem an offer for an order. The offer row is locked (SELECT .. FOR UPDATE) so concurrent
    redemptions can never exceed max_redemptions / max_per_customer. Same order id again = idempotent replay.
    """
    offer = await get_offer_by_code(db, code, lock=True)
    if offer is None:
        await db.rollback()
        return {"redeemed": False, "reason_code": "OFFER_NOT_FOUND", "reason": engine.REASON_MESSAGES["OFFER_NOT_FOUND"]}

    # Copy what we need from the ORM objects now: rollback()/commit() expire them, and touching an
    # expired object in async code raises MissingGreenlet.
    offer_id, offer_code = offer.id, offer.code

    existing = (
        await db.execute(
            select(OfferRedemption).where(OfferRedemption.offer_id == offer_id, OfferRedemption.order_ref == order_ref)
        )
    ).scalar_one_or_none()
    if existing is not None:
        replay = {
            "redeemed": True,
            "duplicate": True,
            "offer_id": str(offer_id),
            "code": offer_code,
            "discount_amount": float(existing.discount_amount),
            "free_shipping": existing.free_shipping,
        }
        await db.rollback()
        return replay

    verdict = await check(db, offer, user_id=user_id, order_value=order_value, categories=categories)
    if not verdict["valid"]:
        await db.rollback()
        return {"redeemed": False, "reason_code": verdict["reason_code"], "reason": verdict["reason"]}

    now = datetime.now(timezone.utc)
    db.add(
        OfferRedemption(
            offer_id=offer_id,
            external_user_id=user_id,
            order_ref=order_ref,
            order_value=order_value,
            discount_amount=verdict["discount_amount"],
            free_shipping=verdict["free_shipping"],
            redeemed_at=now,
        )
    )
    await events_service.ingest_events(
        db,
        [
            EventIn(
                event_type=EventType.OFFER_REDEEM,
                external_user_id=user_id,
                session_id=order_ref,
                timestamp=now,
                platform=Platform.UNKNOWN,
                metadata={
                    "offer_code": offer_code,
                    "offer_id": str(offer_id),
                    "order_id": order_ref,
                    "discount_amount": verdict["discount_amount"],
                },
                idempotency_key=_hash("offer-redeem", str(offer_id), order_ref),
            )
        ],
    )
    await db.commit()
    return {
        "redeemed": True,
        "duplicate": False,
        "offer_id": str(offer_id),
        "code": offer_code,
        "discount_amount": verdict["discount_amount"],
        "free_shipping": verdict["free_shipping"],
        "final_value": verdict["final_value"],
    }


# ------------------------------------------------------------------- overviews
async def totals(db: AsyncSession) -> dict:
    """All-time and 30-day numbers for the offers dashboard and the analytics overview."""
    since = datetime.now(timezone.utc) - timedelta(days=30)
    now = datetime.now(timezone.utc)

    async def interactions(action: str, after: datetime | None = None) -> int:
        query = select(func.count()).select_from(OfferInteraction).where(OfferInteraction.action == action)
        if after is not None:
            query = query.where(OfferInteraction.occurred_at >= after)
        return int((await db.execute(query)).scalar_one())

    async def redemptions(after: datetime | None = None) -> tuple[int, float, float]:
        query = select(
            func.count(),
            func.coalesce(func.sum(OfferRedemption.discount_amount), 0),
            func.coalesce(func.sum(OfferRedemption.order_value), 0),
        ).select_from(OfferRedemption)
        if after is not None:
            query = query.where(OfferRedemption.redeemed_at >= after)
        n, discount, revenue = (await db.execute(query)).one()
        return int(n), round(float(discount), 2), round(float(revenue), 2)

    offers = (await db.execute(select(Offer))).scalars().all()
    by_status: dict[str, int] = {s: 0 for s in engine.STATUSES}
    active_now = 0
    for offer in offers:
        by_status[offer.status] = by_status.get(offer.status, 0) + 1
        if engine.effective_status(to_rule(offer), now) == "active":
            active_now += 1

    impressions, clicks = await interactions("impression"), await interactions("click")
    redeemed, discount, revenue = await redemptions()
    redeemed_30, discount_30, revenue_30 = await redemptions(since)
    impressions_30, clicks_30 = await interactions("impression", since), await interactions("click", since)

    return {
        "offers": len(offers),
        "by_status": by_status,
        "active_now": active_now,
        "all_time": {
            "impressions": impressions,
            "clicks": clicks,
            "redemptions": redeemed,
            "discount_given": discount,
            "revenue": revenue,
            "ctr": round(clicks / impressions, 4) if impressions else None,
            "redemption_rate": round(redeemed / impressions, 4) if impressions else None,
        },
        "last_30d": {
            "impressions": impressions_30,
            "clicks": clicks_30,
            "redemptions": redeemed_30,
            "discount_given": discount_30,
            "revenue": revenue_30,
        },
    }
