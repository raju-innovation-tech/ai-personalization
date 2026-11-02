import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.events.schemas import _contains_nul
from app.segments.definitions import SEGMENT_KEYS

_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,63}$")

OfferType = Literal["percent_off", "fixed_off", "free_shipping"]


def normalize_code(value: str) -> str:
    return value.strip().upper()


class OfferIn(BaseModel):
    code: str = Field(..., min_length=3, max_length=64, description="Coupon code, e.g. WELCOME10 (stored in upper case)")
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    offer_type: OfferType
    value: float = Field(default=0, ge=0, le=100_000_000, description="Percent (1-100) or fixed amount; ignored for free_shipping")
    max_discount: float | None = Field(default=None, gt=0, le=100_000_000)
    min_order_value: float | None = Field(default=None, ge=0, le=100_000_000)
    max_redemptions: int | None = Field(default=None, ge=1, le=100_000_000, description="Total budget; empty = unlimited")
    max_per_customer: int = Field(default=1, ge=1, le=1000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    target_segments: list[str] = Field(default_factory=list, max_length=12, description="Empty = every customer")
    target_categories: list[str] = Field(default_factory=list, max_length=50, description="Empty = every category")
    priority: int = Field(default=50, ge=0, le=100)

    @field_validator("code")
    @classmethod
    def valid_code(cls, v: str) -> str:
        v = normalize_code(v)
        if not _CODE_RE.match(v):
            raise ValueError("code may only contain A-Z, 0-9, '_' and '-' (3-64 characters)")
        return v

    @field_validator("name", "description", "target_categories")
    @classmethod
    def no_nul(cls, v):
        if _contains_nul(v):
            raise ValueError("value must not contain the NUL character")
        return v

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("target_segments")
    @classmethod
    def known_segments(cls, v: list[str]) -> list[str]:
        unknown = [s for s in v if s not in SEGMENT_KEYS]
        if unknown:
            raise ValueError(f"unknown segment(s): {', '.join(unknown)}")
        return list(dict.fromkeys(v))

    @field_validator("target_categories")
    @classmethod
    def clean_categories(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(c.strip() for c in v if c.strip()))

    @field_validator("starts_at", "ends_at")
    @classmethod
    def timezone_required(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("must include a timezone offset (e.g. 'Z' or '+05:30')")
        return v

    @model_validator(mode="after")
    def check_rules(self) -> "OfferIn":
        if self.offer_type == "percent_off" and not (0 < self.value <= 100):
            raise ValueError("percent_off needs a value between 0 and 100")
        if self.offer_type == "fixed_off" and self.value <= 0:
            raise ValueError("fixed_off needs a value greater than 0")
        if self.offer_type == "free_shipping":
            self.value = 0
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class StatusIn(BaseModel):
    status: Literal["draft", "active", "paused", "ended"]


class OfferTrackIn(BaseModel):
    code: str = Field(..., min_length=3, max_length=64)
    external_user_id: str = Field(..., min_length=1, max_length=128)
    action: Literal["impression", "click"]
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
    timestamp: datetime | None = None

    @field_validator("code")
    @classmethod
    def upper(cls, v: str) -> str:
        return normalize_code(v)

    @field_validator("timestamp")
    @classmethod
    def timezone_required(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("must include a timezone offset (e.g. 'Z' or '+05:30')")
        return v


class OfferCheckIn(BaseModel):
    """Used by checkout: validate a code, then redeem it once the order is placed."""

    code: str = Field(..., min_length=3, max_length=64)
    external_user_id: str = Field(..., min_length=1, max_length=128)
    order_value: float = Field(..., ge=0, le=1_000_000_000)
    categories: list[str] = Field(default_factory=list, max_length=100, description="Product categories in the cart")

    @field_validator("code")
    @classmethod
    def upper(cls, v: str) -> str:
        return normalize_code(v)


class OfferRedeemIn(OfferCheckIn):
    order_id: str = Field(..., min_length=1, max_length=128, description="Your order id - makes the call idempotent")
