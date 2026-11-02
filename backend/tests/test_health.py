import pytest

pytestmark = pytest.mark.asyncio


async def test_health_endpoint(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"


async def test_ready_endpoint_reports_database_check(client):
    response = await client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()["data"]
    assert "checks" in body
    assert "database" in body["checks"]
