"""
Welfog -> AI engine data mapping.  Pure Python (standard library only): no database,
no web code, so every rule here is unit-tested without any infrastructure.

Welfog facts this module is built on (checked against the real MySQL / Postgres dumps):

* customer id   : ``orders.user_id`` / ``carts.user_id`` / ``wishlists.user_id`` hold
                  ``customers.user_id``  ->  ``external_user_id``
* product id    : those tables hold the Postgres ``products.pro_id`` (NOT ``products.id``)
                  ->  ``product_id``
* ``orders``    : one row per purchased line.  ``price`` is the LINE total
                  (``sp_price * quantity``); ``grand_total`` adds shipping.
* order status  : ``delivery_status`` (``status`` is always 1).  Most rows are unpaid COD
                  orders that were auto-cancelled; those never completed and are skipped.
* ``brand``     : "No Brand" / "Non-Branded" / blank mean "unknown", not a real brand.
"""
from __future__ import annotations

import html
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

# Must stay in sync with app.database.models.event.EventType / Platform
# (tests/test_welfog_mapping.py compares them).
VALID_EVENT_TYPES = frozenset(
    {
        "PRODUCT_VIEW", "PRODUCT_SEARCH", "CATEGORY_VIEW", "WISHLIST_ADD", "WISHLIST_REMOVE",
        "ADD_TO_CART", "REMOVE_FROM_CART", "CHECKOUT_STARTED", "PURCHASE", "PURCHASE_CANCELLED",
        "RETURN", "PRODUCT_REVIEW", "OFFER_VIEW", "OFFER_CLICK", "OFFER_REDEEM",
        "RECOMMENDATION_VIEW", "RECOMMENDATION_CLICK",
    }
)
VALID_PLATFORMS = frozenset({"web", "mobile", "ios", "android", "unknown"})
PLACEHOLDER_BRANDS = frozenset(
    {"", "no brand", "nobrand", "non-branded", "non branded", "nonbranded", "unbranded", "none", "null", "n/a", "na"}
)
CANCELLED_STATUSES = frozenset({"cancelled", "canceled"})

MAX_PRICE = 100_000_000.0
_TAG_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"\s+")


# ------------------------------------------------------------------ options / results
@dataclass(frozen=True)
class MapOptions:
    # Timezone the Welfog servers store naive DATETIME / TIMESTAMP values in.
    # Everything sent to the engine is converted to UTC.
    source_tz: str = "UTC"
    # Base URL for relative product image paths (e.g. https://cdn.welfog.com/uploads/).
    image_base_url: str | None = None
    # Once the tracking SQL (user_events + triggers) is live, cart / wishlist rows created at or
    # after this instant are already captured there; skipping them here prevents double counting.
    events_table_start: datetime | None = None


@dataclass
class MapResult:
    events: list[dict] = field(default_factory=list)
    skipped: str | None = None  # reason when nothing was produced


@dataclass
class ProductResult:
    product: dict | None = None
    skipped: str | None = None


# ------------------------------------------------------------------------- primitives
def to_float(value) -> float | None:
    """Numbers, Decimals and numeric strings; rejects bools, NaN, inf and junk."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float, Decimal)):
            number = float(value)
        elif isinstance(value, str):
            number = float(value.strip())
        else:
            return None
    except (ValueError, InvalidOperation, OverflowError):
        return None
    return number if math.isfinite(number) else None


def to_int(value) -> int | None:
    number = to_float(value)
    return None if number is None else int(number)


def clean_text(value, max_len: int) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\x00", "").strip()
    if not text:
        return None
    return text[:max_len]


def strip_html(value, max_len: int) -> str | None:
    if value is None:
        return None
    text = html.unescape(_TAG_RE.sub(" ", str(value)))
    text = _WS_RE.sub(" ", text.replace("\x00", "")).strip()
    return text[:max_len] if text else None


def to_id(value, max_len: int = 128) -> str | None:
    """Integer-like or text id -> clean string. None for empty / zero / too long."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (float, Decimal)):
        number = float(value)
        if not math.isfinite(number):
            return None
        if number.is_integer():
            value = int(number)
    text = str(value).replace("\x00", "").strip()
    if not text or len(text) > max_len:
        return None
    if text.isdigit() and int(text) == 0:
        return None
    return text


def _tz(name: str):
    if not name or name.upper() == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception as exc:  # unknown zone or missing tz database
        raise ValueError(f"Unknown timezone {name!r} (pip install tzdata if the OS has no tz database)") from exc


def to_utc(value, source_tz: str = "UTC") -> datetime | None:
    """datetime / ISO string -> timezone-aware UTC datetime. Naive values are read in source_tz."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip()
        if not text or text.startswith("0000"):
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.year < 2000:  # MySQL zero / placeholder dates
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz(source_tz))
    return dt.astimezone(timezone.utc)


def _norm(value) -> str:
    return str(value).strip().lower() if value is not None else ""


def _platform(value) -> str:
    text = _norm(value)
    return text if text in VALID_PLATFORMS else "unknown"


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _clean_meta(meta: dict) -> dict:
    out = {}
    for key, value in meta.items():
        value = _json_safe(value)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        out[key] = value.replace("\x00", "") if isinstance(value, str) else value
    return out


def _event(*, event_type, user_id, product_id, ts, key, session_id=None, platform=None, metadata=None) -> dict | None:
    if event_type not in VALID_EVENT_TYPES or ts is None or not key or len(key) > 255:
        return None
    return {
        "event_type": event_type,
        "external_user_id": user_id,
        "product_id": product_id,
        "session_id": clean_text(session_id, 128),
        "platform": _platform(platform),
        "timestamp": ts.isoformat(),
        "metadata": _clean_meta(metadata or {}),
        "idempotency_key": key,
    }


# ----------------------------------------------------------------------------- products
def map_product(row: dict, opts: MapOptions = MapOptions()) -> ProductResult:
    """Postgres ``products`` row -> body item for ``POST /products/bulk``."""
    product_id = to_id(row.get("pro_id"))
    if product_id is None:
        return ProductResult(skipped="no_pro_id")
    name = clean_text(row.get("name"), 500)
    if name is None:
        return ProductResult(skipped="no_name")

    price = to_float(row.get("unit_price"))
    if price is not None and not (0 <= price <= MAX_PRICE):
        price = None

    stock = to_int(row.get("stock"))
    in_stock = True if stock is None else stock > 0
    is_active = (
        to_int(row.get("published")) == 1
        and to_int(row.get("approved")) == 1
        and not to_int(row.get("hold"))
        and not to_int(row.get("block"))
    )

    brand = clean_text(row.get("brand"), 255)
    if brand is None or brand.lower() in PLACEHOLDER_BRANDS:
        brand = None  # a fake shared "No Brand" would make all unbranded products look alike

    rating = to_float(row.get("rating"))
    if rating is not None and not (0 <= rating <= 5):
        rating = None

    tags: list[str] = []
    for tag in str(row.get("tags") or "").split(","):
        tag = clean_text(tag, 100)
        if tag and tag.lower() not in {t.lower() for t in tags} and len(tags) < 50:
            tags.append(tag)

    features = None
    raw_features = row.get("pro_features")
    if isinstance(raw_features, dict):
        features = raw_features
    elif isinstance(raw_features, str) and raw_features.strip().startswith("{"):
        try:
            parsed = json.loads(raw_features)
            features = parsed if isinstance(parsed, dict) else None
        except ValueError:
            features = None

    attributes = _clean_meta(
        {
            "welfog_id": to_int(row.get("id")),
            "category_id": to_int(row.get("category_id")),
            "sku": clean_text(row.get("sku"), 128),
            "color": clean_text(row.get("color_name"), 100),
            "size": clean_text(row.get("size"), 100),
            "num_of_sale": to_int(row.get("num_of_sale")),
            "features": features,
        }
    )

    return ProductResult(
        product={
            "product_id": product_id,
            "name": name,
            "description": strip_html(row.get("description"), 10000),
            "category": clean_text(row.get("category_name"), 255),
            "brand": brand,
            "price": price,
            "image_url": _image_url(row, opts),
            "rating": rating,
            "tags": tags,
            "is_active": is_active,
            "in_stock": in_stock,
            "attributes": attributes,
        }
    )


def _image_url(row: dict, opts: MapOptions) -> str | None:
    path = clean_text(row.get("thumb_url") or row.get("thumbnail_img"), 1000)
    if not path:
        return None
    if path.lower().startswith(("http://", "https://")):
        return path
    if to_int(row.get("img_is_url")) == 1:
        return None  # flagged as a URL but is not one -> do not send a broken link
    if not opts.image_base_url:
        return None
    url = opts.image_base_url.rstrip("/") + "/" + path.lstrip("/")
    return url if len(url) <= 1000 else None


# ------------------------------------------------------------------------------ orders
def map_order(row: dict, opts: MapOptions = MapOptions()) -> MapResult:
    """MySQL ``orders`` row -> PURCHASE (+ PURCHASE_CANCELLED or RETURN) events."""
    user_id = to_id(row.get("user_id"))
    if user_id is None:
        return MapResult(skipped="no_user")
    product_id = to_id(row.get("product_id"))
    if product_id is None:
        return MapResult(skipped="no_product")
    order_id = to_id(row.get("oid")) or to_id(row.get("id"))
    if order_id is None:
        return MapResult(skipped="no_order_id")
    created = to_utc(row.get("created_at"), opts.source_tz)
    if created is None:
        return MapResult(skipped="no_timestamp")
    updated = to_utc(row.get("updated_at"), opts.source_tz) or created
    updated = max(updated, created)

    status = _norm(row.get("delivery_status"))
    paid = _norm(row.get("payment_status")) == "paid"
    cancelled = status in CANCELLED_STATUSES
    if cancelled and not paid:
        return MapResult(skipped="cancelled_unpaid")  # checkout never completed

    quantity = to_int(row.get("quantity"))
    quantity = quantity if quantity and quantity >= 1 else 1
    line_total = to_float(row.get("price"))
    if line_total is None or line_total < 0:
        unit = to_float(row.get("sp_price"))
        line_total = unit * quantity if unit is not None and unit >= 0 else None
    discount = max(to_float(row.get("coupon_discount")) or 0.0, 0.0) + max(to_float(row.get("coin_discount")) or 0.0, 0.0)
    amount = None if line_total is None else round(max(line_total - discount, 0.0), 2)

    meta = {
        "amount": amount,
        "quantity": quantity,
        "unit_price": to_float(row.get("sp_price")),
        "order_id": order_id,
        "shipping_cost": to_float(row.get("shipping_cost")),
        "grand_total": to_float(row.get("grand_total")),
        "payment_mode": clean_text(row.get("payment_mode"), 30),
        "payment_status": _norm(row.get("payment_status")) or None,
        "delivery_status": status or None,
        "source": "welfog.orders",
    }
    # One checkout basket = same customer + same minute (Welfog has no basket id:
    # combined_order_id is empty). Used by the engine to count orders and find "bought together".
    session_id = clean_text(row.get("session_id"), 128) or f"basket:{user_id}:{created:%Y%m%d%H%M}"
    common = dict(user_id=user_id, product_id=product_id, session_id=session_id, platform=row.get("platform"))

    events = [
        _event(event_type="PURCHASE", ts=created, key=f"welfog:order:{order_id}:purchase", metadata=meta, **common)
    ]
    if cancelled:  # paid, then cancelled -> refund
        events.append(
            _event(event_type="PURCHASE_CANCELLED", ts=updated, key=f"welfog:order:{order_id}:cancelled", metadata=meta, **common)
        )
    elif _norm(row.get("return_status")) == "completed":
        events.append(
            _event(event_type="RETURN", ts=updated, key=f"welfog:order:{order_id}:return", metadata=meta, **common)
        )
    events = [e for e in events if e]
    return MapResult(events=events, skipped=None if events else "invalid")


# -------------------------------------------------------------- cart / wishlist / review
def _covered_by_events_table(created: datetime, opts: MapOptions) -> bool:
    start = opts.events_table_start
    if start is None:
        return False
    if start.tzinfo is None:
        start = start.replace(tzinfo=_tz(opts.source_tz))
    return created >= start


def map_cart(row: dict, opts: MapOptions = MapOptions()) -> MapResult:
    """MySQL ``carts`` row -> ADD_TO_CART. Guest rows (no user_id) cannot be attributed."""
    user_id, product_id = to_id(row.get("user_id")), to_id(row.get("product_id"))
    row_id = to_id(row.get("id"))
    created = to_utc(row.get("created_at"), opts.source_tz)
    if user_id is None:
        return MapResult(skipped="guest_or_no_user")
    if product_id is None or row_id is None or created is None:
        return MapResult(skipped="incomplete")
    if _covered_by_events_table(created, opts):
        return MapResult(skipped="covered_by_user_events")
    quantity = to_int(row.get("quantity"))
    event = _event(
        event_type="ADD_TO_CART", user_id=user_id, product_id=product_id, ts=created, key=f"welfog:cart:{row_id}",
        session_id=row.get("session_id"), platform=row.get("platform"),
        metadata={"quantity": quantity if quantity and quantity >= 1 else 1, "price": to_float(row.get("price")), "source": "welfog.carts"},
    )
    return MapResult(events=[event]) if event else MapResult(skipped="invalid")


def map_wishlist(row: dict, opts: MapOptions = MapOptions()) -> MapResult:
    user_id, product_id = to_id(row.get("user_id")), to_id(row.get("product_id"))
    row_id = to_id(row.get("id"))
    created = to_utc(row.get("created_at"), opts.source_tz)
    if user_id is None or product_id is None or row_id is None or created is None:
        return MapResult(skipped="incomplete")
    if _covered_by_events_table(created, opts):
        return MapResult(skipped="covered_by_user_events")
    event = _event(
        event_type="WISHLIST_ADD", user_id=user_id, product_id=product_id, ts=created,
        key=f"welfog:wishlist:{row_id}", metadata={"source": "welfog.wishlists"},
    )
    return MapResult(events=[event]) if event else MapResult(skipped="invalid")


def map_review(row: dict, opts: MapOptions = MapOptions()) -> MapResult:
    user_id, product_id = to_id(row.get("user_id")), to_id(row.get("product_id"))
    row_id = to_id(row.get("id"))
    created = to_utc(row.get("created_at"), opts.source_tz)
    if user_id is None or product_id is None or row_id is None or created is None:
        return MapResult(skipped="incomplete")
    rating = to_float(row.get("rating"))
    event = _event(
        event_type="PRODUCT_REVIEW", user_id=user_id, product_id=product_id, ts=created,
        key=f"welfog:review:{row_id}",
        metadata={
            "rating": rating if rating is not None and 0 <= rating <= 5 else None,
            "order_id": to_id(row.get("order_id")),
            "source": "welfog.reviews",
        },
    )
    return MapResult(events=[event]) if event else MapResult(skipped="invalid")


def map_user_event(row: dict, opts: MapOptions = MapOptions()) -> MapResult:
    """Row of the new ``user_events`` tracking table (see docs/welfog_mysql_tracking.sql)."""
    event_type = str(row.get("event_type") or "").strip().upper()
    if event_type not in VALID_EVENT_TYPES:
        return MapResult(skipped="unknown_event_type")
    user_id = to_id(row.get("user_id"))
    if user_id is None:
        return MapResult(skipped="guest_or_no_user")
    row_id = to_id(row.get("id"))
    ts = to_utc(row.get("occurred_at"), "UTC")  # the tracking table always stores UTC
    if row_id is None or ts is None:
        return MapResult(skipped="incomplete")
    extra = row.get("metadata")
    if isinstance(extra, (str, bytes)):
        try:
            extra = json.loads(extra)
        except ValueError:
            extra = None
    meta = dict(extra) if isinstance(extra, dict) else {}
    meta.update({"query": clean_text(row.get("search_query"), 500), "category_id": to_int(row.get("category_id")), "source": "welfog.user_events"})
    event = _event(
        event_type=event_type, user_id=user_id, product_id=to_id(row.get("product_id")), ts=ts,
        key=f"welfog:ue:{row_id}", session_id=row.get("session_id"), platform=row.get("platform"), metadata=meta,
    )
    return MapResult(events=[event]) if event else MapResult(skipped="invalid")
