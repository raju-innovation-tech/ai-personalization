import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_roles, verify_storefront_auth
from app.core.logging import get_logger
from app.core.responses import NotFoundError, success_response
from app.database.database import get_db
from app.database.models.user import User, UserRole
from app.experiments import service as experiments_service
from app.offers import service
from app.offers.schemas import OfferCheckIn, OfferIn, OfferRedeemIn, OfferTrackIn, StatusIn

logger = get_logger(__name__)

router = APIRouter(prefix="/offers", tags=["Offers"])

# Marketing people manage campaigns; checkout integrations validate/redeem with the same roles.
_manager = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.MARKETING_MANAGER)


async def _offer_or_404(db: AsyncSession, offer_id: uuid.UUID):
    offer = await service.get_offer(db, offer_id)
    if offer is None:
        raise NotFoundError(f"Offer '{offer_id}' not found", code="OFFER_NOT_FOUND")
    return offer


# ------------------------------------------------------------ storefront (open / api-key protected)
@router.get("/user/{external_user_id}", summary="Personalised offers for a customer", dependencies=[Depends(verify_storefront_auth)])
async def offers_for_user(
    external_user_id: str,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    category: str | None = Query(default=None, max_length=255, description="Category being browsed"),
    cart_value: Annotated[float | None, Query(ge=0)] = None,
    db: AsyncSession = Depends(get_db),
):
    # A/B test: a running "offers" experiment may restrict which offers this customer can see.
    assignment = await experiments_service.assign_for_request(db, "offers", external_user_id)
    codes = assignment.config.get("offer_codes") if assignment else None
    ranked = await service.offers_for_user(
        db,
        external_user_id,
        limit=limit,
        browsing_category=category,
        order_value=cart_value,
        allowed_codes=set(codes) if codes is not None else None,
    )
    return success_response(
        {
            "external_user_id": external_user_id,
            "experiment": assignment.public() if assignment else None,
            "count": len(ranked),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": [service.public_offer_out(r) for r in ranked],
        }
    )


@router.post("/track", status_code=201, summary="Track an offer impression or click", dependencies=[Depends(verify_storefront_auth)])
async def track(payload: OfferTrackIn, db: AsyncSession = Depends(get_db)):
    offer = await service.get_offer_by_code(db, payload.code)
    if offer is None:
        raise NotFoundError(f"Offer '{payload.code}' not found", code="OFFER_NOT_FOUND")
    stored = await service.track(
        db,
        offer,
        user_id=payload.external_user_id,
        action=payload.action,
        idempotency_key=payload.idempotency_key,
        when=payload.timestamp or datetime.now(timezone.utc),
    )
    return success_response({"status": "accepted" if stored else "duplicate"})


# ----------------------------------------------------- checkout (login required)
@router.post("/validate", summary="Check a coupon code for a customer and order (checkout)")
async def validate(payload: OfferCheckIn, db: AsyncSession = Depends(get_db), _user: User = Depends(_manager)):
    offer = await service.get_offer_by_code(db, payload.code)
    result = await service.check(
        db, offer, user_id=payload.external_user_id, order_value=payload.order_value, categories=payload.categories
    )
    return success_response(result)


@router.post("/redeem", summary="Redeem a coupon for a placed order (idempotent by order_id)")
async def redeem(payload: OfferRedeemIn, db: AsyncSession = Depends(get_db), _user: User = Depends(_manager)):
    result = await service.redeem(
        db,
        code=payload.code,
        user_id=payload.external_user_id,
        order_ref=payload.order_id,
        order_value=payload.order_value,
        categories=payload.categories,
    )
    if result["redeemed"]:
        logger.info("offer_redeemed", code=result["code"], duplicate=result.get("duplicate"))
    return success_response(result)


# ------------------------------------------------------------- admin (read: any user)
@router.get("/stats", summary="Offer KPIs for the dashboard")
async def stats(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return success_response(await service.totals(db))


@router.get("", summary="List offers with performance")
async def list_offers(
    status: Literal["draft", "active", "paused", "ended"] | None = None,
    q: str | None = Query(default=None, max_length=200, description="Matches name or code"),
    sort: Literal["created", "name", "priority", "ends"] = "created",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    rows, total = await service.list_offers(db, status=status, q=q, sort=sort, page=page, page_size=page_size)
    stats_by_id = await service.stats_for(db, [r.id for r in rows])
    now = datetime.now(timezone.utc)
    return success_response(
        {
            "items": [service.offer_out(r, stats_by_id.get(r.id), now) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }
    )


@router.get("/{offer_id}", summary="One offer with performance")
async def get_offer(offer_id: uuid.UUID, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    offer = await _offer_or_404(db, offer_id)
    stats_by_id = await service.stats_for(db, [offer.id])
    return success_response(service.offer_out(offer, stats_by_id.get(offer.id)))


# ------------------------------------------------------------ admin (write: marketing+)
@router.post("", status_code=201, summary="Create an offer (starts as draft)")
async def create_offer(payload: OfferIn, db: AsyncSession = Depends(get_db), user: User = Depends(_manager)):
    offer = await service.create_offer(db, payload, created_by=user.email)
    logger.info("offer_created", code=offer.code, by=user.email)
    return success_response(service.offer_out(offer))


@router.put("/{offer_id}", summary="Edit an offer (code cannot change)")
async def update_offer(
    offer_id: uuid.UUID, payload: OfferIn, db: AsyncSession = Depends(get_db), _user: User = Depends(_manager)
):
    offer = await _offer_or_404(db, offer_id)
    offer = await service.update_offer(db, offer, payload)
    stats_by_id = await service.stats_for(db, [offer.id])
    return success_response(service.offer_out(offer, stats_by_id.get(offer.id)))


@router.post("/{offer_id}/status", summary="Activate, pause or end an offer")
async def change_status(
    offer_id: uuid.UUID, payload: StatusIn, db: AsyncSession = Depends(get_db), user: User = Depends(_manager)
):
    offer = await _offer_or_404(db, offer_id)
    offer = await service.change_status(db, offer, payload.status)
    logger.info("offer_status_changed", code=offer.code, status=offer.status, by=user.email)
    stats_by_id = await service.stats_for(db, [offer.id])
    return success_response(service.offer_out(offer, stats_by_id.get(offer.id)))
