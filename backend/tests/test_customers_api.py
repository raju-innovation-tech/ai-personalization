import asyncio
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio


def ts(days_ago=0.0):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def ev(event_type, user, product=None, session="s", days_ago=0.0, **metadata):
    return {
        "event_type": event_type, "external_user_id": user, "product_id": product,
        "session_id": session, "timestamp": ts(days_ago), "metadata": metadata,
    }


async def seed(client, admin_headers):
    await client.post("/api/v1/products/bulk", json={"products": [
        {"product_id": "P1", "name": "Alpha Laptop", "category": "Laptops", "brand": "Acme", "price": 100},
        {"product_id": "P2", "name": "Beta Mouse", "category": "Accessories", "brand": "Zeta", "price": 50},
    ]}, headers=admin_headers)
    events = [
        # c1: order s1 = P1 x2 (200) + P2 (50); order s2 = P1 (100); P2 returned (-50) -> 300, 2 orders
        ev("PRODUCT_VIEW", "c1", "P1", "s0", 9),
        ev("PURCHASE", "c1", "P1", "s1", 8, quantity=2),
        ev("PURCHASE", "c1", "P2", "s1", 8),
        ev("PURCHASE", "c1", "P1", "s2", 3),
        ev("RETURN", "c1", "P2", "s3", 2),
        # c2: browsing only
        ev("PRODUCT_VIEW", "c2", "P2", "b1", 1),
        ev("ADD_TO_CART", "c2", "P2", "b1", 1),
        # c3: one recent order with an explicit amount
        ev("PURCHASE", "c3", "P2", "o1", 5, amount=400),
        # c4: only ancient activity (outside the 365 day lookback)
        ev("PRODUCT_VIEW", "c4", "P1", "old", 400),
    ]
    r = await client.post("/api/v1/events/batch", json={"events": events})
    assert r.status_code == 201, r.text
    recompute = await client.post("/api/v1/customers/recompute", headers=admin_headers)
    assert recompute.status_code == 200, recompute.text
    return recompute.json()["data"]


async def test_read_endpoints_require_auth(client):
    for path in ("/customers", "/customers/stats", "/customers/x", "/customers/x/timeline", "/segments", "/segments/champions"):
        assert (await client.get(f"/api/v1{path}")).status_code == 401, path


async def test_recompute_requires_admin(client, viewer_headers):
    assert (await client.post("/api/v1/customers/recompute")).status_code == 401
    assert (await client.post("/api/v1/customers/recompute", headers=viewer_headers)).status_code == 403


async def test_profile_math_orders_spend_returns(client, admin_headers):
    summary = await seed(client, admin_headers)
    assert summary["customers"] == 4 and summary["buyers"] == 2
    c1 = (await client.get("/api/v1/customers/c1", headers=admin_headers)).json()["data"]
    s = c1["stats"]
    assert s["orders"] == 2                 # sessions s1 and s2
    assert s["items_purchased"] == 4        # 2 + 1 + 1
    assert s["total_spend"] == 300.0        # 200 + 50 + 100 - 50 (returned mouse)
    assert s["avg_order_value"] == 150.0
    assert s["returns"] == 1
    assert s["recency_days"] == 3
    assert s["views"] == 1 and s["events"] == 5
    assert c1["favorite_category"] == "Laptops" and c1["favorite_brand"] == "Acme"
    assert len(c1["rfm"]["code"]) == 3
    assert c1["segment"]["key"] and c1["segment"]["description"] and c1["segment"]["action"]


async def test_non_buyers_and_old_activity(client, admin_headers):
    await seed(client, admin_headers)
    c2 = (await client.get("/api/v1/customers/c2", headers=admin_headers)).json()["data"]
    assert c2["segment"]["key"] == "prospect" and c2["rfm"]["code"] is None
    assert c2["stats"]["cart_adds"] == 1
    c3 = (await client.get("/api/v1/customers/c3", headers=admin_headers)).json()["data"]
    assert c3["segment"]["key"] == "new_customer" and c3["stats"]["total_spend"] == 400.0
    c4 = (await client.get("/api/v1/customers/c4", headers=admin_headers)).json()["data"]
    assert c4["segment"]["key"] == "inactive" and c4["stats"]["events"] == 0   # outside the lookback


async def test_recompute_is_idempotent(client, admin_headers):
    await seed(client, admin_headers)
    before = (await client.get("/api/v1/customers/c1", headers=admin_headers)).json()["data"]["stats"]
    again = await client.post("/api/v1/customers/recompute", headers=admin_headers)
    assert again.status_code == 200
    after = (await client.get("/api/v1/customers/c1", headers=admin_headers)).json()["data"]["stats"]
    assert before == after


async def test_concurrent_recompute_never_500(client, admin_headers):
    await seed(client, admin_headers)
    responses = await asyncio.gather(*[client.post("/api/v1/customers/recompute", headers=admin_headers) for _ in range(4)])
    assert {r.status_code for r in responses} <= {200, 409}
    assert any(r.status_code == 200 for r in responses)
    for r in responses:
        if r.status_code == 409:
            assert r.json()["error"]["code"] == "RECOMPUTE_IN_PROGRESS"


async def test_list_filter_sort_search_paginate(client, admin_headers):
    await seed(client, admin_headers)
    base = "/api/v1/customers"
    everyone = (await client.get(base, headers=admin_headers)).json()["data"]
    assert everyone["total"] == 4

    by_spend = (await client.get(f"{base}?sort=spend&order=desc", headers=admin_headers)).json()["data"]["items"]
    assert [c["customer_id"] for c in by_spend][:2] == ["c3", "c1"]       # 400 then 300

    prospects = (await client.get(f"{base}?segment=prospect", headers=admin_headers)).json()["data"]
    assert [c["customer_id"] for c in prospects["items"]] == ["c2"]

    assert (await client.get(f"{base}?q=C3", headers=admin_headers)).json()["data"]["total"] == 1

    page2 = (await client.get(f"{base}?page_size=3&page=2", headers=admin_headers)).json()["data"]
    assert (page2["total_pages"], len(page2["items"])) == (2, 1)

    bad = await client.get(f"{base}?segment=nope", headers=admin_headers)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_SEGMENT"
    assert (await client.get(f"{base}?sort=bogus", headers=admin_headers)).status_code == 422
    assert (await client.get(f"{base}?page_size=500", headers=admin_headers)).status_code == 422


async def test_detail_and_timeline(client, admin_headers):
    await seed(client, admin_headers)
    assert (await client.get("/api/v1/customers/ghost", headers=admin_headers)).json()["error"]["code"] == "CUSTOMER_NOT_FOUND"
    assert (await client.get("/api/v1/customers/ghost/timeline", headers=admin_headers)).status_code == 404

    t = (await client.get("/api/v1/customers/c1/timeline?page_size=2", headers=admin_headers)).json()["data"]
    assert t["total"] == 5 and t["total_pages"] == 3 and len(t["items"]) == 2
    assert t["items"][0]["event_type"] == "RETURN"                      # newest first
    assert t["items"][0]["product_name"] == "Beta Mouse" and t["items"][0]["category"] == "Accessories"
    last = (await client.get("/api/v1/customers/c1/timeline?page_size=2&page=3", headers=admin_headers)).json()["data"]
    assert [i["event_type"] for i in last["items"]] == ["PRODUCT_VIEW"]  # oldest


async def test_stats_overview(client, admin_headers):
    await seed(client, admin_headers)
    d = (await client.get("/api/v1/customers/stats", headers=admin_headers)).json()["data"]
    t = d["totals"]
    assert (t["customers"], t["buyers"], t["repeat_buyers"], t["repeat_rate"]) == (4, 2, 1, 0.5)
    assert t["revenue"] == 700.0 and t["orders"] == 3 and t["avg_order_value"] == round(700 / 3, 2)
    assert d["top_spenders"][0]["customer_id"] == "c3" and d["profiles_computed_at"]


async def test_segments_overview_includes_all_segments_and_grid(client, admin_headers):
    await seed(client, admin_headers)
    d = (await client.get("/api/v1/segments", headers=admin_headers)).json()["data"]
    assert len(d["segments"]) == 12 and d["total_customers"] == 4
    assert sum(s["customers"] for s in d["segments"]) == 4
    assert abs(sum(s["share"] for s in d["segments"]) - 1.0) < 0.01
    assert abs(sum(s["revenue"] for s in d["segments"]) - 700.0) < 0.01
    assert sum(g["count"] for g in d["rfm_grid"]) == 2                   # only buyers are scored
    one = (await client.get("/api/v1/segments/prospect", headers=admin_headers)).json()["data"]
    assert one["customers"] == 1 and one["action"]
    assert (await client.get("/api/v1/segments/nope", headers=admin_headers)).json()["error"]["code"] == "SEGMENT_NOT_FOUND"


async def test_empty_database(client, admin_headers):
    r = await client.post("/api/v1/customers/recompute", headers=admin_headers)
    assert r.json()["data"]["customers"] == 0
    d = (await client.get("/api/v1/segments", headers=admin_headers)).json()["data"]
    assert d["total_customers"] == 0 and len(d["segments"]) == 12 and d["rfm_grid"] == []
    stats = (await client.get("/api/v1/customers/stats", headers=admin_headers)).json()["data"]
    assert stats["totals"]["repeat_rate"] is None and stats["totals"]["avg_order_value"] is None


async def test_new_customers_seen_via_events_get_a_row_even_before_recompute(client, admin_headers):
    await client.post("/api/v1/events", json=ev("PRODUCT_VIEW", "fresh", None, "x"))
    row = (await client.get("/api/v1/customers/fresh", headers=admin_headers)).json()["data"]
    assert row["segment"] is None and row["stats"]["orders"] == 0       # not scored until recompute
