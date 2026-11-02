from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_roles
from app.core.logging import get_logger
from app.core.responses import NotFoundError, success_response
from app.database.database import get_db
from app.database.models.user import User, UserRole
from app.products import service
from app.products.schemas import ProductBulkIn, ProductIn

logger = get_logger(__name__)

router = APIRouter(prefix="/products", tags=["Products"])

_writer = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.get("", summary="List products (search, filter, sort, paginate)")
async def list_products(
    q: str | None = Query(default=None, max_length=200, description="Matches name, product id or brand"),
    category: str | None = Query(default=None, max_length=255),
    brand: str | None = Query(default=None, max_length=255),
    in_stock: bool | None = None,
    include_inactive: bool = False,
    sort: Literal["name", "price", "rating", "created"] = "name",
    order: Literal["asc", "desc"] = "asc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    rows, total = await service.list_products(
        db,
        q=q,
        category=category,
        brand=brand,
        in_stock=in_stock,
        active_only=not include_inactive,
        sort=sort,
        descending=order == "desc",
        page=page,
        page_size=page_size,
    )
    return success_response(
        {
            "items": [service.to_out(r).model_dump(mode="json") for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }
    )


@router.get("/filters", summary="Distinct categories and brands (for filter dropdowns)")
async def filters(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return success_response(await service.distinct_values(db))


@router.get("/{product_id}", summary="Get one product")
async def get_product(
    product_id: str, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)
):
    row = await service.get_by_external_id(db, product_id)
    if row is None:
        raise NotFoundError(f"Product '{product_id}' not found", code="PRODUCT_NOT_FOUND")
    return success_response(service.to_out(row).model_dump(mode="json"))


@router.post("", summary="Create or update one product (admin)")
async def upsert_product(
    payload: ProductIn, db: AsyncSession = Depends(get_db), _user: User = Depends(_writer)
):
    created, _updated = await service.upsert_products(db, [payload])
    row = await service.get_by_external_id(db, payload.product_id)
    logger.info("product_upserted", product_id=payload.product_id, created=bool(created))
    return success_response({"created": bool(created), "product": service.to_out(row).model_dump(mode="json")})


@router.post("/bulk", summary="Create or update up to 500 products (admin)")
async def upsert_products_bulk(
    payload: ProductBulkIn, db: AsyncSession = Depends(get_db), _user: User = Depends(_writer)
):
    created, updated = await service.upsert_products(db, payload.products)
    logger.info("products_bulk_upserted", created=created, updated=updated)
    return success_response({"created": created, "updated": updated, "total": created + updated})
