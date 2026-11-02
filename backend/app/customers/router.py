from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_roles
from app.core.responses import ApiError, ConflictError, NotFoundError, success_response
from app.customers import service
from app.database.database import get_db
from app.database.models.user import User, UserRole
from app.segments.definitions import SEGMENT_BY_KEY

router = APIRouter(prefix="/customers", tags=["Customers"])


def _check_segment(segment: str | None) -> None:
    if segment is not None and segment not in SEGMENT_BY_KEY:
        raise ApiError(
            "INVALID_SEGMENT",
            f"Unknown segment '{segment}'. Valid: {', '.join(SEGMENT_BY_KEY)}",
            status_code=422,
        )


@router.get("", summary="List customers (search, segment filter, sort, paginate)")
async def list_customers(
    q: str | None = Query(default=None, max_length=128, description="Matches the customer id"),
    segment: str | None = Query(default=None, max_length=40),
    sort: Literal["last_seen", "spend", "orders", "recency", "events", "rfm"] = "last_seen",
    order: Literal["asc", "desc"] = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    _check_segment(segment)
    rows, total = await service.list_customers(
        db, q=q, segment=segment, sort=sort, descending=order == "desc", page=page, page_size=page_size
    )
    return success_response(
        {
            "items": [service.customer_out(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }
    )


@router.get("/stats", summary="Customer KPIs for the dashboard")
async def stats(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return success_response(await service.customer_overview(db))


@router.post("/recompute", summary="Recompute profiles, RFM scores and segments now (admin)")
async def recompute(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)),
):
    summary = await service.recompute_profiles(db)
    if summary is None:
        raise ConflictError("A recompute is already running. Try again in a moment.", code="RECOMPUTE_IN_PROGRESS")
    return success_response(summary)


@router.get("/{external_user_id}", summary="Full customer profile")
async def get_customer(
    external_user_id: str, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)
):
    row = await service.get_customer(db, external_user_id)
    if row is None:
        raise NotFoundError(f"Customer '{external_user_id}' not found", code="CUSTOMER_NOT_FOUND")
    return success_response(service.customer_out(row, detail=True))


@router.get("/{external_user_id}/timeline", summary="Behaviour timeline (newest first)")
async def timeline(
    external_user_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if await service.get_customer(db, external_user_id) is None:
        raise NotFoundError(f"Customer '{external_user_id}' not found", code="CUSTOMER_NOT_FOUND")
    items, total = await service.customer_timeline(db, external_user_id, page, page_size)
    return success_response(
        {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }
    )
