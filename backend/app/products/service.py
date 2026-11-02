import uuid

from sqlalchemy import Select, asc, desc, func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.product import Product
from app.products.schemas import ProductIn, ProductOut
from app.recommendations.service import snapshot_cache

_SORTS = {
    "name": Product.name,
    "price": Product.price,
    "rating": Product.rating,
    "created": Product.created_at,
}


def to_out(row: Product) -> ProductOut:
    return ProductOut(
        product_id=row.external_product_id,
        name=row.name,
        description=row.description,
        category=row.category,
        brand=row.brand,
        price=float(row.price) if row.price is not None else None,
        image_url=row.image_url,
        rating=float(row.rating) if row.rating is not None else None,
        tags=[str(t) for t in (row.tags or [])],
        is_active=row.is_active,
        in_stock=row.in_stock,
        attributes=row.attributes or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def upsert_products(db: AsyncSession, products: list[ProductIn]) -> tuple[int, int]:
    """
    Race-safe bulk upsert (INSERT .. ON CONFLICT DO UPDATE). Returns (created, updated).
    Duplicate ids inside one request: the last one wins.
    """
    deduped: dict[str, ProductIn] = {}
    for product in products:
        deduped[product.product_id] = product

    rows = [
        {
            "id": uuid.uuid4(),
            "external_product_id": pid,
            "name": p.name,
            "description": p.description,
            "category": p.category,
            "brand": p.brand,
            "price": p.price,
            "image_url": p.image_url,
            "rating": p.rating,
            "tags": p.tags,
            "is_active": p.is_active,
            "in_stock": p.in_stock,
            "attributes": p.attributes,
        }
        for pid, p in sorted(deduped.items())  # sorted => consistent lock order
    ]

    stmt = pg_insert(Product).values(rows)
    update_cols = {
        col: getattr(stmt.excluded, col)
        for col in (
            "name", "description", "category", "brand", "price", "image_url",
            "rating", "tags", "is_active", "in_stock", "attributes",
        )
    }
    update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(index_elements=[Product.external_product_id], set_=update_cols)
    # xmax = 0 only for freshly inserted rows (PostgreSQL system column)
    result = await db.execute(stmt.returning(literal_column("(xmax = 0)").label("inserted")))
    flags = [bool(r[0]) for r in result.all()]
    await db.commit()
    snapshot_cache.invalidate()  # catalog changed -> recommendations must see it
    created = sum(flags)
    return created, len(flags) - created


def _filtered(query: Select, *, q, category, brand, in_stock, active_only) -> Select:
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(Product.name.ilike(like), Product.external_product_id.ilike(like), Product.brand.ilike(like))
        )
    if category:
        query = query.where(Product.category == category)
    if brand:
        query = query.where(Product.brand == brand)
    if in_stock is not None:
        query = query.where(Product.in_stock == in_stock)
    if active_only:
        query = query.where(Product.is_active.is_(True))
    return query


async def list_products(
    db: AsyncSession,
    *,
    q: str | None,
    category: str | None,
    brand: str | None,
    in_stock: bool | None,
    active_only: bool,
    sort: str,
    descending: bool,
    page: int,
    page_size: int,
) -> tuple[list[Product], int]:
    filters = dict(q=q, category=category, brand=brand, in_stock=in_stock, active_only=active_only)
    total = (await db.execute(_filtered(select(func.count()).select_from(Product), **filters))).scalar_one()

    column = _SORTS.get(sort, Product.name)
    order = desc(column).nulls_last() if descending else asc(column).nulls_last()
    query = _filtered(select(Product), **filters).order_by(order, Product.external_product_id)
    rows = (await db.execute(query.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return list(rows), int(total)


async def get_by_external_id(db: AsyncSession, product_id: str) -> Product | None:
    return (
        await db.execute(select(Product).where(Product.external_product_id == product_id))
    ).scalar_one_or_none()


async def distinct_values(db: AsyncSession) -> dict[str, list[str]]:
    categories = (
        await db.execute(select(Product.category).where(Product.category.is_not(None)).distinct().order_by(Product.category))
    ).scalars().all()
    brands = (
        await db.execute(select(Product.brand).where(Product.brand.is_not(None)).distinct().order_by(Product.brand))
    ).scalars().all()
    return {"categories": list(categories), "brands": list(brands)}
