from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------- API
def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def ev(event_type, user, product=None, session=None, days=1.0, **metadata):
    return {"event_type": event_type, "external_user_id": user, "product_id": product, "session_id": session,
            "timestamp": ago(days), "metadata": metadata, "platform": "web"}


async def seed(client, admin_headers):
    await client.post("/api/v1/products/bulk", json={"products": [
        {"product_id": "P1", "name": "Laptop One", "category": "Laptops", "price": 1000},
        {"product_id": "P2", "name": "Phone Two", "category": "Phones", "price": 500},
    ]}, headers=admin_headers)
    events = [
        # --- current 7 days: u1 buys 2 laptops, u2 buys a phone and returns it, u3 only browses
        ev("PRODUCT_VIEW", "u1", "P1", "a", 2), ev("ADD_TO_CART", "u1", "P1", "a", 2), ev("CHECKOUT_STARTED", "u1", None, "a", 2),
        ev("PURCHASE", "u1", "P1", "a", 2, quantity=2),
        ev("PRODUCT_VIEW", "u2", "P2", "b", 3), ev("ADD_TO_CART", "u2", "P2", "b", 3), ev("CHECKOUT_STARTED", "u2", None, "b", 3),
        ev("PURCHASE", "u2", "P2", "b", 3), ev("RETURN", "u2", "P2", "c", 1),
        ev("PRODUCT_VIEW", "u3", "P1", "d", 1),
        # --- previous 7 days: one purchase of a laptop
        ev("PRODUCT_VIEW", "u9", "P1", "z", 11), ev("PURCHASE", "u9", "P1", "z", 11),
    ]
    assert (await client.post("/api/v1/events/batch", json={"events": events})).status_code == 201


async def test_report_requires_auth_and_validates_days(client, admin_headers):
    assert (await client.get("/api/v1/analytics/report")).status_code == 401
    assert (await client.get("/api/v1/analytics/report?days=0", headers=admin_headers)).status_code == 422
    assert (await client.get("/api/v1/analytics/report?days=400", headers=admin_headers)).status_code == 422


async def test_report_on_empty_database(client, admin_headers):
    d = (await client.get("/api/v1/analytics/report?days=14", headers=admin_headers)).json()["data"]
    assert d["days"] == 14 and len(d["daily"]) == 14
    assert d["kpis"]["revenue"]["value"] == 0 and d["kpis"]["revenue"]["change"] is None
    assert [f["customers"] for f in d["funnel"]] == [0, 0, 0, 0]
    assert d["top_products"] == [] and d["top_categories"] == [] and d["platforms"] == []


async def test_report_numbers(client, admin_headers):
    await seed(client, admin_headers)
    d = (await client.get("/api/v1/analytics/report?days=7", headers=admin_headers)).json()["data"]
    k = d["kpis"]
    assert k["revenue"] == {"value": 2000.0, "previous": 1000.0, "change": 1.0}      # 2x1000 + 500 - 500 (return)
    assert k["orders"]["value"] == 2 and k["orders"]["previous"] == 1                # sessions a and b
    assert k["avg_order_value"]["value"] == 1000.0 and k["avg_order_value"]["change"] == 0.0
    assert k["active_customers"] == {"value": 3.0, "previous": 1.0, "change": 2.0}
    assert k["conversion_rate"]["value"] == round(2 / 3, 2)                           # u1, u2 bought / 3 active
    assert k["events"]["value"] == 10 and k["events"]["previous"] == 2

    assert len(d["daily"]) == 7 and d["daily"][-1]["date"] == d["to"]
    assert sum(day["events"] for day in d["daily"]) == 10
    assert round(sum(day["revenue"] for day in d["daily"]), 2) == 2000.0

    assert [(f["step"], f["customers"]) for f in d["funnel"]] == [("viewed", 3), ("carted", 2), ("checkout", 2), ("purchased", 2)]
    assert d["funnel"][1]["rate_from_start"] == round(2 / 3, 4)

    top = d["top_products"]
    assert [p["product_id"] for p in top] == ["P1"]                                  # P2 netted to zero -> not a top product
    assert top[0]["name"] == "Laptop One" and top[0]["units"] == 2 and top[0]["revenue"] == 2000.0 and top[0]["views"] == 2
    assert d["top_categories"] == [{"category": "Laptops", "revenue": 2000.0, "share": 1.0}]
    assert d["platforms"] == [{"platform": "web", "events": 10, "share": 1.0}]


async def test_report_period_length_changes_the_window(client, admin_headers):
    await seed(client, admin_headers)
    wide = (await client.get("/api/v1/analytics/report?days=30", headers=admin_headers)).json()["data"]
    assert wide["kpis"]["revenue"]["value"] == 3000.0 and wide["kpis"]["orders"]["value"] == 3    # includes the older purchase
    assert wide["kpis"]["revenue"]["previous"] == 0 and wide["kpis"]["revenue"]["change"] is None


async def test_report_includes_offers_and_recommendations(client, admin_headers):
    await seed(client, admin_headers)
    offer = (await client.post("/api/v1/offers", json={"code": "RPT10", "name": "Report", "offer_type": "percent_off", "value": 10}, headers=admin_headers)).json()["data"]
    await client.post(f"/api/v1/offers/{offer['id']}/status", json={"status": "active"}, headers=admin_headers)
    await client.post("/api/v1/offers/track", json={"code": "RPT10", "external_user_id": "u1", "action": "impression"})
    await client.post("/api/v1/offers/redeem", json={"code": "RPT10", "external_user_id": "u1", "order_id": "R1", "order_value": 1000}, headers=admin_headers)
    await client.get("/api/v1/recommendations/popular")
    today = (await client.get("/api/v1/analytics/report?days=7", headers=admin_headers)).json()["data"]["daily"][-1]
    assert today["offer_impressions"] == 1 and today["offer_redemptions"] == 1 and today["offer_discount"] == 100.0
    assert today["recs_served"] == 1
