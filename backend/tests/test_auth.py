import pytest

from app.core.security import hash_password
from app.database.models.user import User, UserRole

pytestmark = pytest.mark.asyncio


async def _create_user(db_session, email="admin@test.com", password="Password123!", role=UserRole.SUPER_ADMIN):
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name="Test Admin",
        role=role,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def test_login_success(client, db_session):
    await _create_user(db_session)

    response = await client.post(
        "/api/v1/auth/login", json={"email": "admin@test.com", "password": "Password123!"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "access_token" in body["data"]
    assert "refresh_token" in body["data"]


async def test_login_wrong_password(client, db_session):
    await _create_user(db_session)

    response = await client.post(
        "/api/v1/auth/login", json={"email": "admin@test.com", "password": "WrongPassword"}
    )

    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_CREDENTIALS"


async def test_me_requires_token(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_full_login_me_refresh_logout_flow(client, db_session):
    await _create_user(db_session)

    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": "admin@test.com", "password": "Password123!"}
    )
    tokens = login_resp.json()["data"]

    me_resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["email"] == "admin@test.com"

    refresh_resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_resp.status_code == 200
    new_tokens = refresh_resp.json()["data"]
    assert new_tokens["access_token"] != tokens["access_token"]

    logout_resp = await client.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {new_tokens['access_token']}"}
    )
    assert logout_resp.status_code == 200

    # Old refresh token should now be rejected (rotated away).
    stale_refresh = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert stale_refresh.status_code == 401


async def test_refresh_token_cannot_be_used_twice_concurrently(client, db_session):
    import asyncio

    await _create_user(db_session)
    tokens = (
        await client.post("/api/v1/auth/login", json={"email": "admin@test.com", "password": "Password123!"})
    ).json()["data"]

    responses = await asyncio.gather(
        *[client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}) for _ in range(4)]
    )
    codes = sorted(r.status_code for r in responses)
    assert codes.count(200) == 1
    assert codes.count(401) == 3


async def test_access_token_is_not_accepted_as_refresh_token(client, db_session):
    await _create_user(db_session)
    tokens = (
        await client.post("/api/v1/auth/login", json={"email": "admin@test.com", "password": "Password123!"})
    ).json()["data"]
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert response.status_code == 401
