from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.events.schemas import _contains_nul


class ProductIn(BaseModel):
    """Catalog item pushed by the e-commerce platform (upsert by `product_id`)."""

    product_id: str = Field(..., min_length=1, max_length=128, description="Your own product id / SKU")
    name: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=10000)
    category: str | None = Field(default=None, max_length=255)
    brand: str | None = Field(default=None, max_length=255)
    price: float | None = Field(default=None, ge=0, le=100_000_000)
    image_url: str | None = Field(default=None, max_length=1000)
    rating: float | None = Field(default=None, ge=0, le=5)
    tags: list[str] = Field(default_factory=list, max_length=50)
    is_active: bool = True
    in_stock: bool = True
    attributes: dict = Field(default_factory=dict)

    @field_validator("product_id", "name", "description", "category", "brand", "image_url", "tags", "attributes")
    @classmethod
    def reject_nul_characters(cls, v):
        if _contains_nul(v):
            raise ValueError("value must not contain the NUL character")
        return v

    @field_validator("product_id", "name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class ProductBulkIn(BaseModel):
    products: list[ProductIn] = Field(..., min_length=1, max_length=500)


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    name: str
    description: str | None
    category: str | None
    brand: str | None
    price: float | None
    image_url: str | None
    rating: float | None
    tags: list[str]
    is_active: bool
    in_stock: bool
    attributes: dict
    created_at: datetime
    updated_at: datetime
