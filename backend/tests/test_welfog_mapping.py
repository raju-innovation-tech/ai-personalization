"""Welfog -> engine mapping rules. Pure Python: no database, no web server."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.integrations.welfog import mapping
from app.integrations.welfog.mapping import MapOptions

# Row shapes copied from the real Welfog dumps.
ORDER = {
    "id": 2602081, "oid": 2602081, "user_id": 1113, "product_id": 2603914, "quantity": 1,
    "price": 70, "sp_price": 70, "shipping_cost": 99, "grand_total": Decimal("169.00"),
    "coupon_discount": Decimal("0.00"), "coin_discount": Decimal("0.00"), "payment_mode": "Prepaid",
    "payment_status": "paid", "delivery_status": "Delivered", "return_status": None,
    "created_at": datetime(2026, 2, 8, 16, 27, 37), "updated_at": datetime(2026, 2, 10, 9, 0, 0),
}
PRODUCT = {
    "id": 1323, "pro_id": 2619412, "name": "Men's Premium White Sports Sneakers", "category_id": 13178,
    "category_name": "Sneakers", "brand": "No Brand", "unit_price": "999", "stock": 20, "published": 1,
    "approved": 1, "hold": 0, "block": 0, "rating": None, "tags": None, "sku": "SNS-WHT-10",
    "color_name": "White", "size": "10", "num_of_sale": 0, "img_is_url": 0,
    "thumb_url": "1649/1649-130726-490915.webp",
    "description": "<p>Experience the <strong>perfect</strong> combination &amp; comfort</p>",
    "pro_features": '{"Pack of":"1"}',
}


def order(**changes):
    return {**ORDER, **changes}


# -------------------------------------------------------------------------- contract
def test_event_types_and_platforms_match_the_engine():
    from app.database.models.event import EventType, Platform

    assert mapping.VALID_EVENT_TYPES == {e.value for e in EventType}
    assert mapping.VALID_PLATFORMS == {p.value for p in Platform}


# --------------------------------------------------------------------------- products
def test_product_maps_real_row():
    p = mapping.map_product(PRODUCT, MapOptions(image_base_url="https://cdn.example.com/uploads/")).product
    assert p["product_id"] == "2619412"  # pro_id, never products.id
    assert p["price"] == 999.0 and p["category"] == "Sneakers"
    assert p["brand"] is None  # "No Brand" is not a brand
    assert p["is_active"] is True and p["in_stock"] is True
    assert p["description"] == "Experience the perfect combination & comfort"
    assert p["image_url"] == "https://cdn.example.com/uploads/1649/1649-130726-490915.webp"
    assert p["attributes"]["color"] == "White" and p["attributes"]["welfog_id"] == 1323
    assert p["attributes"]["features"] == {"Pack of": "1"}


@pytest.mark.parametrize("brand", ["No Brand", "Non-Branded", "", "  ", None])
def test_placeholder_brands_become_none(brand):
    assert mapping.map_product({**PRODUCT, "brand": brand}).product["brand"] is None


def test_real_brand_is_kept():
    assert mapping.map_product({**PRODUCT, "brand": "Nike"}).product["brand"] == "Nike"


@pytest.mark.parametrize("flag", ["published", "approved"])
def test_unpublished_or_unapproved_is_inactive(flag):
    assert mapping.map_product({**PRODUCT, flag: 0}).product["is_active"] is False


@pytest.mark.parametrize("flag", ["hold", "block"])
def test_hold_or_block_is_inactive(flag):
    assert mapping.map_product({**PRODUCT, flag: 1}).product["is_active"] is False


def test_stock_zero_is_out_of_stock_and_unknown_stock_is_in_stock():
    assert mapping.map_product({**PRODUCT, "stock": 0}).product["in_stock"] is False
    assert mapping.map_product({**PRODUCT, "stock": None}).product["in_stock"] is True


def test_product_without_id_or_name_is_skipped():
    assert mapping.map_product({**PRODUCT, "pro_id": None}).skipped == "no_pro_id"
    assert mapping.map_product({**PRODUCT, "name": "  "}).skipped == "no_name"


@pytest.mark.parametrize("raw", ["abc", "-5", None, "1e12"])
def test_bad_price_becomes_none(raw):
    assert mapping.map_product({**PRODUCT, "unit_price": raw}).product["price"] is None


def test_relative_image_without_base_url_is_not_sent():
    assert mapping.map_product(PRODUCT).product["image_url"] is None
    full = {**PRODUCT, "thumb_url": "https://x.example/a.jpg", "img_is_url": 1}
    assert mapping.map_product(full).product["image_url"] == "https://x.example/a.jpg"


def test_tags_are_split_deduplicated_and_capped():
    tags = mapping.map_product({**PRODUCT, "tags": "shoes, Shoes ,, sneakers"}).product["tags"]
    assert tags == ["shoes", "sneakers"]


def test_rating_outside_0_to_5_is_dropped():
    assert mapping.map_product({**PRODUCT, "rating": "4.5"}).product["rating"] == 4.5
    assert mapping.map_product({**PRODUCT, "rating": 9}).product["rating"] is None


# ----------------------------------------------------------------------------- orders
def test_normal_order_is_one_purchase():
    result = mapping.map_order(ORDER)
    assert result.skipped is None and len(result.events) == 1
    e = result.events[0]
    assert e["event_type"] == "PURCHASE"
    assert e["external_user_id"] == "1113" and e["product_id"] == "2603914"
    assert e["timestamp"] == "2026-02-08T16:27:37+00:00"
    assert e["idempotency_key"] == "welfog:order:2602081:purchase"
    assert e["metadata"]["amount"] == 70.0 and e["metadata"]["quantity"] == 1
    assert e["metadata"]["grand_total"] == 169.0  # kept for reference, NOT used as the value


def test_amount_is_the_line_total_not_price_times_quantity_again():
    e = mapping.map_order(order(quantity=2, price=214, sp_price=107, grand_total=412)).events[0]
    assert e["metadata"]["amount"] == 214.0 and e["metadata"]["quantity"] == 2


def test_amount_falls_back_to_unit_price_times_quantity():
    e = mapping.map_order(order(quantity=3, price=None, sp_price=100)).events[0]
    assert e["metadata"]["amount"] == 300.0


def test_discounts_reduce_the_amount_but_never_below_zero():
    assert mapping.map_order(order(coupon_discount=10, coin_discount=5)).events[0]["metadata"]["amount"] == 55.0
    assert mapping.map_order(order(coupon_discount=500)).events[0]["metadata"]["amount"] == 0.0


def test_unpaid_cod_order_in_hold_is_still_a_purchase():
    result = mapping.map_order(order(payment_status="unpaid", payment_mode="COD", delivery_status="hold"))
    assert [e["event_type"] for e in result.events] == ["PURCHASE"]


@pytest.mark.parametrize("status", ["cancelled", "Cancelled", "canceled"])
def test_cancelled_unpaid_order_is_skipped(status):
    result = mapping.map_order(order(payment_status="unpaid", delivery_status=status))
    assert result.events == [] and result.skipped == "cancelled_unpaid"


def test_cancelled_paid_order_is_purchase_then_cancellation():
    result = mapping.map_order(order(delivery_status="cancelled"))
    purchase, cancelled = result.events
    assert (purchase["event_type"], cancelled["event_type"]) == ("PURCHASE", "PURCHASE_CANCELLED")
    assert purchase["metadata"]["amount"] == cancelled["metadata"]["amount"]  # refund nets the spend to 0
    assert cancelled["timestamp"] >= purchase["timestamp"]
    assert cancelled["idempotency_key"] == "welfog:order:2602081:cancelled"


def test_cancellation_time_never_precedes_purchase_time():
    result = mapping.map_order(order(delivery_status="cancelled", updated_at=datetime(2025, 1, 1)))
    assert result.events[1]["timestamp"] == result.events[0]["timestamp"]


def test_completed_return_adds_a_return_event_but_cancelled_return_does_not():
    assert [e["event_type"] for e in mapping.map_order(order(return_status="Completed")).events] == ["PURCHASE", "RETURN"]
    assert [e["event_type"] for e in mapping.map_order(order(return_status="Canceled")).events] == ["PURCHASE"]


def test_order_without_user_product_or_time_is_skipped():
    assert mapping.map_order(order(user_id=None)).skipped == "no_user"
    assert mapping.map_order(order(product_id=None)).skipped == "no_product"
    assert mapping.map_order(order(created_at=None)).skipped == "no_timestamp"


def test_naive_timestamps_are_read_in_the_configured_timezone_and_sent_as_utc():
    ist = mapping.map_order(ORDER, MapOptions(source_tz="Asia/Kolkata")).events[0]
    assert ist["timestamp"] == "2026-02-08T10:57:37+00:00"
    assert mapping.map_order(ORDER).events[0]["timestamp"] == "2026-02-08T16:27:37+00:00"


def test_same_customer_same_minute_shares_a_basket_session():
    a = mapping.map_order(order(oid=1, id=1, created_at=datetime(2026, 5, 1, 10, 30, 5))).events[0]
    b = mapping.map_order(order(oid=2, id=2, created_at=datetime(2026, 5, 1, 10, 30, 50))).events[0]
    c = mapping.map_order(order(oid=3, id=3, created_at=datetime(2026, 5, 1, 10, 31, 0))).events[0]
    assert a["session_id"] == b["session_id"] != c["session_id"]
    explicit = mapping.map_order(order(session_id="web-abc")).events[0]
    assert explicit["session_id"] == "web-abc"


def test_platform_is_normalised():
    assert mapping.map_order(order(platform="Android")).events[0]["platform"] == "android"
    assert mapping.map_order(order(platform="nokia")).events[0]["platform"] == "unknown"
    assert mapping.map_order(ORDER).events[0]["platform"] == "unknown"


# ------------------------------------------------------- cart / wishlist / review / events
CART = {"id": 7, "user_id": 519, "product_id": 2603914, "price": 70.0, "quantity": 2, "created_at": datetime(2026, 9, 1, 8, 0, 0)}


def test_cart_row_becomes_add_to_cart():
    e = mapping.map_cart(CART).events[0]
    assert e["event_type"] == "ADD_TO_CART" and e["metadata"]["quantity"] == 2
    assert e["idempotency_key"] == "welfog:cart:7"


def test_guest_cart_is_skipped_and_zero_quantity_counts_as_one():
    assert mapping.map_cart({**CART, "user_id": None}).skipped == "guest_or_no_user"
    assert mapping.map_cart({**CART, "quantity": 0}).events[0]["metadata"]["quantity"] == 1


def test_rows_already_captured_by_the_tracking_table_are_skipped():
    opts = MapOptions(events_table_start=datetime(2026, 9, 1, 0, 0, 0))
    assert mapping.map_cart(CART, opts).skipped == "covered_by_user_events"
    assert mapping.map_cart({**CART, "created_at": datetime(2026, 8, 31, 23, 59, 59)}, opts).events
    wish = {"id": 3, "user_id": 519, "product_id": 5, "created_at": datetime(2026, 9, 2)}
    assert mapping.map_wishlist(wish, opts).skipped == "covered_by_user_events"
    assert mapping.map_wishlist(wish).events[0]["event_type"] == "WISHLIST_ADD"


def test_review_keeps_only_a_valid_rating():
    row = {"id": 1, "user_id": 9, "product_id": 5, "order_id": 77, "rating": 4, "created_at": datetime(2026, 3, 1)}
    assert mapping.map_review(row).events[0]["metadata"]["rating"] == 4.0
    assert "rating" not in mapping.map_review({**row, "rating": 11}).events[0]["metadata"]


def test_tracking_table_rows_are_mapped_as_utc():
    row = {"id": 5, "user_id": 519, "event_type": "product_view", "product_id": 2603914, "category_id": 10382,
           "search_query": None, "session_id": "s1", "platform": "ios", "metadata": '{"k": 1}',
           "occurred_at": datetime(2026, 11, 1, 12, 0, 0, 123000)}
    e = mapping.map_user_event(row, MapOptions(source_tz="Asia/Kolkata")).events[0]
    assert e["event_type"] == "PRODUCT_VIEW" and e["platform"] == "ios"
    assert e["timestamp"].startswith("2026-11-01T12:00:00.123")  # source_tz is NOT applied to this table
    assert e["metadata"]["k"] == 1 and e["metadata"]["category_id"] == 10382
    assert mapping.map_user_event({**row, "event_type": "NOPE"}).skipped == "unknown_event_type"
    assert mapping.map_user_event({**row, "user_id": None}).skipped == "guest_or_no_user"


# ------------------------------------------------------------------------- primitives
def test_to_id():
    assert mapping.to_id(Decimal("5.00")) == "5" and mapping.to_id(12.0) == "12"
    assert mapping.to_id(0) is None and mapping.to_id("  ") is None and mapping.to_id(None) is None
    assert mapping.to_id("x" * 129) is None and mapping.to_id(True) is None


def test_to_utc_handles_junk():
    assert mapping.to_utc("0000-00-00 00:00:00") is None
    assert mapping.to_utc("not a date") is None
    assert mapping.to_utc(datetime(2026, 1, 1, tzinfo=timezone.utc)).isoformat() == "2026-01-01T00:00:00+00:00"


def test_to_float_rejects_nan_inf_bool():
    assert mapping.to_float("nan") is None and mapping.to_float(float("inf")) is None
    assert mapping.to_float(True) is None and mapping.to_float("12.5") == 12.5


# -------------------------------------------------- everything produced is accepted by the engine
def test_every_produced_payload_passes_the_engine_schemas():
    from app.events.schemas import EventIn
    from app.products.schemas import ProductIn

    events = (
        mapping.map_order(order(delivery_status="cancelled", return_status="Completed")).events
        + mapping.map_cart(CART).events
        + mapping.map_wishlist({"id": 3, "user_id": 519, "product_id": 5, "created_at": datetime(2026, 9, 2)}).events
    )
    assert events
    for event in events:
        EventIn(**event)
    ProductIn(**mapping.map_product(PRODUCT).product)
