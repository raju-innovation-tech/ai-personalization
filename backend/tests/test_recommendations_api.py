import pytest

pytestmark = pytest.mark.asyncio

T0 = "2026-10-01T10:00:00Z"


def p(pid, name, category, brand="Acme", price=1000, **kw):
    return {"product_id": pid, "name": name, "category": category, "brand": brand, "price": price, **kw}


async def load_catalog(client, admin_headers):
    await client.post(
        "/api/v1/products/bulk",
        json={"products": [
            p("L1", "Acme Pro Laptop", "Laptops", price=60000),
            p("L2", "Acme Air Laptop", "Laptops", price=55000),
            p("L3", "Zeta Book Laptop", "Laptops", "Zeta", 80000),
            p("B1", "Acme Sleeve Laptop Bag", "Laptop Bags", price=1500),
            p("S1", "Run Fast Shoes", "Running Shoes", "Nike", 5000),
            p("OOS", "Sold Out Laptop", "Laptops", price=61000, in_stock=False),
            p("OFF", "Retired Laptop", "Laptops", price=62000, is_active=False),
        ]},
        headers=admin_headers,
    )


def ev(event_type, user, product, session="s", ts=T0):
    return {"event_type": event_type, "external_user_id": user, "product_id": product, "session_id": session, "timestamp": ts}


async def send(client, events):
    r = await client.post("/api/v1/events/batch", json={"events": events})
    assert r.status_code == 201, r.text


async def test_popular_ranks_and_filters(client, admin_headers):
    await load_catalog(client, admin_headers)
    await send(client, [
        ev("PURCHASE", "u1", "S1", "a"), ev("PURCHASE", "u2", "S1", "b"), ev("PRODUCT_VIEW", "u3", "L1"),
        ev("PURCHASE", "u4", "OOS", "c"), ev("PURCHASE", "u5", "OFF", "d"),
    ])
    body = (await client.get("/api/v1/recommendations/popular?limit=5")).json()["data"]
    ids = [i["product_id"] for i in body["items"]]
    assert ids[0] == "S1" and body["algorithm"] == "popular"
    assert "OOS" not in ids and "OFF" not in ids
    laptops = (await client.get("/api/v1/recommendations/popular?category=laptops")).json()["data"]["items"]
    assert laptops and all(i["category"] == "Laptops" for i in laptops)


async def test_similar_excludes_self_and_unknown_is_404(client, admin_headers):
    await load_catalog(client, admin_headers)
    items = (await client.get("/api/v1/recommendations/similar/L1?limit=3")).json()["data"]["items"]
    ids = [i["product_id"] for i in items]
    assert "L1" not in ids and ids[0] in {"L2", "L3"}
    missing = await client.get("/api/v1/recommendations/similar/NOPE")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


async def test_frequently_bought_together_from_purchase_baskets(client, admin_headers):
    await load_catalog(client, admin_headers)
    events = []
    for n, user in enumerate(("u1", "u2")):
        events += [ev("PURCHASE", user, "L1", f"s{n}"), ev("PURCHASE", user, "B1", f"s{n}")]
    await send(client, events)
    items = (await client.get("/api/v1/recommendations/frequently-bought/L1?limit=3")).json()["data"]["items"]
    assert items[0]["product_id"] == "B1" and items[0]["algorithm"] == "fbt"
    assert "2 orders" in items[0]["reason"]


async def test_user_recommendations_personalised_vs_cold_start(client, admin_headers):
    await load_catalog(client, admin_headers)
    await send(client, [
        ev("PURCHASE", "me", "L1", "m1"), ev("PRODUCT_VIEW", "me", "L2", "m2"),
        ev("PRODUCT_VIEW", "o1", "L1", "o1"), ev("PURCHASE", "o1", "L3", "o1"),
        ev("PRODUCT_VIEW", "o2", "L1", "o2"), ev("PURCHASE", "o2", "L3", "o2"),
    ])
    mine = (await client.get("/api/v1/recommendations/user/me?limit=4")).json()["data"]
    ids = [i["product_id"] for i in mine["items"]]
    assert mine["personalized"] is True and mine["algorithm"] == "hybrid"
    assert "L1" not in ids                      # already bought
    assert ids[0] in {"L2", "L3"}
    assert "OOS" not in ids and "OFF" not in ids

    cold = (await client.get("/api/v1/recommendations/user/stranger?limit=3")).json()["data"]
    assert cold["personalized"] is False and cold["algorithm"] == "popular" and cold["count"] == 3


async def test_home_feed_sections(client, admin_headers):
    await load_catalog(client, admin_headers)
    await send(client, [ev("PRODUCT_VIEW", "me", "L1"), ev("PRODUCT_VIEW", "x", "S1")])
    data = (await client.get("/api/v1/recommendations/home/me?limit=2")).json()["data"]
    assert data["personalized"] is True
    assert [s["key"] for s in data["sections"]][0] == "for_you"
    anon = (await client.get("/api/v1/recommendations/home/stranger")).json()["data"]
    assert [s["key"] for s in anon["sections"]] == ["for_you"] and anon["personalized"] is False


async def test_limit_is_validated(client):
    assert (await client.get("/api/v1/recommendations/popular?limit=0")).status_code == 422
    assert (await client.get("/api/v1/recommendations/popular?limit=999")).status_code == 422


async def test_catalog_change_is_visible_immediately(client, admin_headers):
    await load_catalog(client, admin_headers)
    await client.get("/api/v1/recommendations/popular")          # builds + caches snapshot
    await client.post("/api/v1/products", json=p("NEW", "Brand New Laptop", "Laptops", price=58000), headers=admin_headers)
    ids = [i["product_id"] for i in (await client.get("/api/v1/recommendations/similar/L1?limit=10")).json()["data"]["items"]]
    assert "NEW" in ids


async def test_track_impression_and_click_feed_ctr_and_stats(client, admin_headers):
    await load_catalog(client, admin_headers)
    base = {"external_user_id": "u1", "product_id": "L1", "algorithm": "hybrid"}
    assert (await client.post("/api/v1/recommendations/track", json={**base, "action": "impression"})).status_code == 201
    assert (await client.post("/api/v1/recommendations/track", json={**base, "action": "click"})).status_code == 201
    bad = await client.post("/api/v1/recommendations/track", json={**base, "action": "hover"})
    assert bad.status_code == 422

    await client.get("/api/v1/recommendations/popular")
    await client.get("/api/v1/recommendations/similar/L1")
    overview = (await client.get("/api/v1/analytics/overview", headers=admin_headers)).json()["data"]
    assert overview["recommendation_ctr_30d"] == {"impressions": 1, "clicks": 1, "ctr": 1.0}
    assert overview["totals"]["recommendations_served"] == 2

    status = (await client.get("/api/v1/recommendations/status", headers=admin_headers)).json()["data"]
    assert status["products"] == 7 and status["served_total"] == 2
    assert set(status["served_by_algorithm"]) == {"popular", "similar"}


async def test_status_requires_auth_and_refresh_requires_admin(client, viewer_headers, admin_headers):
    assert (await client.get("/api/v1/recommendations/status")).status_code == 401
    assert (await client.post("/api/v1/recommendations/refresh", headers=viewer_headers)).status_code == 403
    ok = await client.post("/api/v1/recommendations/refresh", headers=admin_headers)
    assert ok.status_code == 200 and "built_at" in ok.json()["data"]


async def test_concurrent_requests_share_one_snapshot_build(client, admin_headers):
    import asyncio

    await load_catalog(client, admin_headers)
    responses = await asyncio.gather(*[client.get("/api/v1/recommendations/popular") for _ in range(10)])
    assert all(r.status_code == 200 for r in responses)
