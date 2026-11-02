"""
Mirrored product catalog (synced from the e-commerce platform via the
products API). Carries the attributes the recommendation engine needs:
category/brand/price/tags for content similarity, plus is_active/in_stock
so we never recommend something the shop cannot sell.
"""
from sqlalchemy import JSON, Boolean, Numeric, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base
from app.database.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"

    external_product_id: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    in_stock: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<Product {self.external_product_id} {self.name!r}>"
