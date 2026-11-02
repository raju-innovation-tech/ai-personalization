from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.responses import success_response
from app.database.database import get_db
from app.database.models.customer import EcommerceCustomer
from app.database.models.offer import Offer
from app.database.models.product import Product
from app.database.models.user import User
from app.segments.definitions import SEGMENT_BY_KEY

router = APIRouter(prefix="/search", tags=["Search"])


def like_pattern(text: str) -> str:
    """Contains-match where the user's % and _ are literal characters, not wildcards."""
    escaped = text.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("", summary="Global search across customers, products and offers")
async def search(
    q: Annotated[str, Query(min_length=2, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    pattern = like_pattern(q)
    customers = (
        await db.execute(
            select(EcommerceCustomer.external_user_id, EcommerceCustomer.segment)
            .where(EcommerceCustomer.external_user_id.ilike(pattern, escape="\\"))
            .order_by(EcommerceCustomer.external_user_id)
            .limit(limit)
        )
    ).all()
    products = (
        await db.execute(
            select(Product.external_product_id, Product.name, Product.category)
            .where(
                Product.name.ilike(pattern, escape="\\")
                | Product.external_product_id.ilike(pattern, escape="\\")
                | Product.brand.ilike(pattern, escape="\\")
            )
            .order_by(Product.name)
            .limit(limit)
        )
    ).all()
    offers = (
        await db.execute(
            select(Offer.id, Offer.code, Offer.name, Offer.status)
            .where(Offer.name.ilike(pattern, escape="\\") | Offer.code.ilike(pattern, escape="\\"))
            .order_by(Offer.code)
            .limit(limit)
        )
    ).all()
    return success_response(
        {
            "query": q,
            "customers": [
                {"id": uid, "segment": SEGMENT_BY_KEY[seg].name if seg in SEGMENT_BY_KEY else None} for uid, seg in customers
            ],
            "products": [{"id": pid, "name": name, "category": category} for pid, name, category in products],
            "offers": [{"id": str(oid), "code": code, "name": name, "status": status} for oid, code, name, status in offers],
        }
    )
