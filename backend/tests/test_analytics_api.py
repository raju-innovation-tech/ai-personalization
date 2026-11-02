import pytest

pytestmark = pytest.mark.asyncio


async def test_overview_requires_auth(client):
    assert (await client.get("/api/v1/analytics/overview")).status_code == 401


async def test_overview_empty_database_has_zeroes_and_full_chart(client, admin_headers):
    data = (await client.get("/api/v1/analytics/overview", headers=admin_headers)).json()["data"]
    assert data["totals"]["customers"] == 0 and data["totals"]["events"] == 0
    assert len(data["events_by_day"]) == 14 and all(d["count"] == 0 for d in data["events_by_day"])
    assert data["recommendation_ctr_30d"]["ctr"] is None


async def test_overview_counts_events_customers_and_categories(client, admin_headers):
    from datetime import datetime, timezone

    await client.post("/api/v1/products", json={"product_id": "A", "name": "A", "category": "Laptops"}, headers=admin_headers)
    now = datetime.now(timezone.utc).isoformat()
    await client.post("/api/v1/events/batch", json={"events": [
        {"event_type": "PRODUCT_VIEW", "external_user_id": "u1", "product_id": "A", "timestamp": now},
        {"event_type": "PURCHASE", "external_user_id": "u2", "product_id": "A", "timestamp": now},
    ]})
    d = (await client.get("/api/v1/analytics/overview", headers=admin_headers)).json()["data"]
    assert d["totals"]["customers"] == 2 and d["totals"]["events"] == 2
    assert d["totals"]["products"] == 1 and d["totals"]["purchases_30d"] == 1
    assert d["events_by_day"][-1]["count"] == 2
    assert d["top_categories"] == [{"category": "Laptops", "interactions": 2}]
    assert {t["event_type"] for t in d["events_by_type"]} == {"PRODUCT_VIEW", "PURCHASE"}
