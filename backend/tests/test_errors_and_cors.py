import pytest

pytestmark = pytest.mark.asyncio


async def test_validation_error_uses_standard_envelope(client):
    response = await client.post("/api/v1/auth/login", json={"email": "not-an-email"})
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]


async def test_unknown_route_uses_standard_envelope(client):
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "error": {"code": "NOT_FOUND", "message": "Not Found"},
    }


async def test_cors_allows_flutter_web_random_localhost_port(client):
    response = await client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:53211",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:53211"


async def test_cors_blocks_unknown_origin(client):
    response = await client.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers
