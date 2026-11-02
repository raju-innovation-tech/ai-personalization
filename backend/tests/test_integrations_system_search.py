from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

pytestmark = pytest.mark.asyncio


def ago(days=0.0):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def ev(event_type, user, product=None, session="s", days=0.0):
    return {"event_type": event_type, "external_user_id": user, "product_id": product, "session_id": session, "timestamp": ago(days)}


# ------------------------------------------------------------------ integrations
async def test_integrations_requires_auth_and_hides_accounts_from_non_admins(client, admin_headers, viewer_headers):
    assert (await client.get("/api/v1/integrations/status")).status_code == 401
    admin_view = (await client.get("/api/v1/integrations/status", headers=admin_headers)).json()["data"]
    viewer_view = (await client.get("/api/v1/integrations/status", headers=viewer_headers)).json()["data"]
    assert {a["email"] for a in admin_view["accounts"]} == {"admin@test.com", "viewer@test.com"}
    assert viewer_view["accounts"] is None
    assert "hashed_password" not in str(admin_view)


async def test_integrations_empty_then_connected(client, admin_headers):
    empty = (await client.get("/api/v1/integrations/status", headers=admin_headers)).json()["data"]
    status = {c["key"]: c["status"] for c in empty["checklist"]}
    assert status["catalog"] == "todo" and status["events"] == "todo" and status["profiles"] == "todo"
    assert status["service_account"] == "warning" and 0 <= empty["score"] < 0.5

    await client.post("/api/v1/products/bulk", json={"products": [{"product_id": "P1", "name": "One", "price": 10}]}, headers=admin_headers)
    events = [ev("PRODUCT_VIEW", "u1", "P1"), ev("PURCHASE", "u1", "P1", "o1"), ev("PRODUCT_VIEW", "u2", "GHOST"), ev("PURCHASE", "u2", "P1", None)]
    await client.post("/api/v1/events/batch", json={"events": events})
    await client.post("/api/v1/customers/recompute", headers=admin_headers)
    await client.get("/api/v1/recommendations/popular")

    d = (await client.get("/api/v1/integrations/status", headers=admin_headers)).json()["data"]
    assert d["catalog"]["products"] == 1 and d["events"]["total"] == 4 and d["events"]["last_24h"] == 4
    assert d["data_quality"]["unknown_product_events_30d"] == 1 and d["data_quality"]["unknown_product_rate"] == 0.25
    assert d["data_quality"]["purchases_without_session_30d"] == 1 and d["data_quality"]["purchases_without_session_rate"] == 0.5
    status = {c["key"]: c["status"] for c in d["checklist"]}
    assert status["catalog"] == status["events"] == status["purchases"] == status["profiles"] == status["recommendations"] == "ok"
    assert status["product_ids"] == "warning" and status["sessions"] == "warning"
    assert d["recommendations"]["served_total"] == 1 and d["profiles"]["last_computed_at"]


# ------------------------------------------------------------------------- system
async def test_system_status_is_admin_only_and_has_no_secrets(client, admin_headers, viewer_headers):
    assert (await client.get("/api/v1/system/status")).status_code == 401
    assert (await client.get("/api/v1/system/status", headers=viewer_headers)).status_code == 403
    d = (await client.get("/api/v1/system/status", headers=admin_headers)).json()["data"]
    assert d["app"]["version"] and d["app"]["uptime_seconds"] >= 0
    assert d["database"]["ok"] is True and d["database"]["size_bytes"] > 0 and d["database"]["latency_ms"] >= 0
    tables = {t["name"]: t["rows"] for t in d["database"]["tables"]}
    assert {"users", "user_events", "products", "offers", "offer_redemptions", "ecommerce_customers"} <= set(tables)
    assert tables["users"] == 2
    assert set(d["redis"]) >= {"ok", "latency_ms", "error"}
    assert d["config"]["reco_lookback_days"] and d["jobs"]["profile_refresh_minutes"] >= 0
    dumped = str(d).lower()
    assert "secret" not in dumped and "password" not in dumped and "postgresql" not in dumped


async def test_alerts_follow_the_state_of_the_system(client, admin_headers, viewer_headers, db_session):
    assert (await client.get("/api/v1/system/alerts")).status_code == 401
    ids = lambda: client.get("/api/v1/system/alerts", headers=viewer_headers)  # noqa: E731

    first = (await ids()).json()["data"]
    assert "no_events" in {a["id"] for a in first["items"]} and first["count"] == first["count"]

    await client.post("/api/v1/products/bulk", json={"products": [
        {"product_id": "P1", "name": "One", "in_stock": False}, {"product_id": "P2", "name": "Two", "in_stock": False},
        {"product_id": "P3", "name": "Three"}]}, headers=admin_headers)
    await client.post("/api/v1/events/batch", json={"events": [ev("PRODUCT_VIEW", "u1", "P1", days=3)]})   # old events only
    found = {a["id"]: a for a in (await ids()).json()["data"]["items"]}
    assert found["events_stale"]["severity"] == "warning" and found["events_stale"]["link"] == "/integrations"
    assert found["stock_low"]["severity"] == "warning" and "2 of 3" in found["stock_low"]["message"]
    assert found["segments_missing"]["link"] == "/segments"
    assert "no_events" not in found

    await client.post("/api/v1/customers/recompute", headers=admin_headers)
    assert "segments_missing" not in {a["id"] for a in (await ids()).json()["data"]["items"]}


async def test_offer_alerts(client, admin_headers, viewer_headers, db_session):
    from app.database.models.offer import Offer

    async def make(code, **kw):
        body = {"code": code, "name": f"Offer {code}", "offer_type": "percent_off", "value": 10, **kw}
        offer = (await client.post("/api/v1/offers", json=body, headers=admin_headers)).json()["data"]
        await client.post(f"/api/v1/offers/{offer['id']}/status", json={"status": "active"}, headers=admin_headers)
        return offer

    ends = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    await make("SOON", ends_at=ends)
    await make("BUDGET", max_redemptions=10, max_per_customer=50)
    await make("OLD")
    for i in range(9):
        await client.post("/api/v1/offers/redeem", json={"code": "BUDGET", "external_user_id": f"u{i}", "order_id": f"o{i}", "order_value": 100}, headers=admin_headers)
    await db_session.execute(update(Offer).where(Offer.code == "OLD").values(ends_at=datetime.now(timezone.utc) - timedelta(hours=1)))
    await db_session.commit()

    items = {a["id"]: a for a in (await client.get("/api/v1/system/alerts", headers=viewer_headers)).json()["data"]["items"]}
    assert items["offer_ending_SOON"]["severity"] == "info"
    assert items["offer_budget_BUDGET"]["severity"] == "warning" and "9 of 10" in items["offer_budget_BUDGET"]["message"]
    assert items["offer_expired_OLD"]["link"] == "/offers"
    body = (await client.get("/api/v1/system/alerts", headers=viewer_headers)).json()["data"]
    severities = [a["severity"] for a in body["items"]]
    assert severities == sorted(severities, key=["critical", "warning", "info"].index)       # most urgent first
    assert body["needs_attention"] == sum(s in ("critical", "warning") for s in severities)


# ------------------------------------------------------------------------- search
async def test_search(client, admin_headers, viewer_headers):
    assert (await client.get("/api/v1/search?q=ab")).status_code == 401
    assert (await client.get("/api/v1/search?q=a", headers=viewer_headers)).status_code == 422          # too short
    assert (await client.get("/api/v1/search?q=ab&limit=99", headers=viewer_headers)).status_code == 422

    await client.post("/api/v1/products/bulk", json={"products": [
        {"product_id": "P_1", "name": "Alpha Laptop", "brand": "Acme"}, {"product_id": "PX1", "name": "Other"}]}, headers=admin_headers)
    offer = (await client.post("/api/v1/offers", json={"code": "ALPHA10", "name": "Alpha deal", "offer_type": "percent_off", "value": 10}, headers=admin_headers)).json()["data"]
    await client.post("/api/v1/events", json=ev("PRODUCT_VIEW", "alpha_user", "P_1"))

    d = (await client.get("/api/v1/search?q=alpha", headers=viewer_headers)).json()["data"]
    assert [c["id"] for c in d["customers"]] == ["alpha_user"]
    assert [p["id"] for p in d["products"]] == ["P_1"] and d["products"][0]["name"] == "Alpha Laptop"
    assert [o["code"] for o in d["offers"]] == ["ALPHA10"] and d["offers"][0]["id"] == offer["id"] and d["offers"][0]["status"] == "draft"

    assert [p["id"] for p in (await client.get("/api/v1/search?q=P_", headers=viewer_headers)).json()["data"]["products"]] == ["P_1"]   # '_' is literal
    nothing = (await client.get("/api/v1/search?q=%25%25", headers=viewer_headers)).json()["data"]                                     # '%%' is literal
    assert nothing["customers"] == nothing["products"] == nothing["offers"] == []
    assert (await client.get("/api/v1/search?q=ACME", headers=viewer_headers)).json()["data"]["products"][0]["id"] == "P_1"             # case-insensitive, brand
