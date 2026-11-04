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


async def test_forgot_password_and_reset_flow(client, db_session):
    from app.auth.service import _IN_MEMORY_OTP_STORE
    _IN_MEMORY_OTP_STORE.clear()

    await _create_user(db_session, email="reset_user@test.com", password="OldPassword123!")

    # 1. Request reset code (OTP dispatched, not returned in body)
    forgot_resp = await client.post("/api/v1/auth/forgot-password", json={"email": "reset_user@test.com"})
    assert forgot_resp.status_code == 200
    forgot_data = forgot_resp.json()["data"]
    assert "reset_code" not in forgot_data
    assert "verification code" in forgot_data["message"].lower()

    # Verify code was generated and stored securely
    otp_record = _IN_MEMORY_OTP_STORE.get("reset_user@test.com")
    assert otp_record is not None
    code = otp_record["code"]
    assert len(code) == 6

    # 2. Resend Cooldown (within 60s should return 429)
    cooldown_resp = await client.post("/api/v1/auth/forgot-password", json={"email": "reset_user@test.com"})
    assert cooldown_resp.status_code == 429
    assert cooldown_resp.json()["error"]["code"] == "OTP_COOLDOWN"

    # 3. Try with wrong code -> should return 401 with remaining attempts
    bad_reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"email": "reset_user@test.com", "code": "000000", "new_password": "NewPassword123!"},
    )
    assert bad_reset.status_code == 401
    assert "4 attempt" in bad_reset.json()["error"]["message"]

    # 4. Reset with correct code -> returns authenticated tokens
    good_reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"email": "reset_user@test.com", "code": code, "new_password": "NewPassword123!"},
    )
    assert good_reset.status_code == 200
    reset_data = good_reset.json()["data"]
    assert "access_token" in reset_data
    assert "refresh_token" in reset_data
    assert reset_data["user"]["email"] == "reset_user@test.com"

    # 5. Old password should fail
    old_login = await client.post(
        "/api/v1/auth/login", json={"email": "reset_user@test.com", "password": "OldPassword123!"}
    )
    assert old_login.status_code == 401

    # 6. New password should succeed
    new_login = await client.post(
        "/api/v1/auth/login", json={"email": "reset_user@test.com", "password": "NewPassword123!"}
    )
    assert new_login.status_code == 200
