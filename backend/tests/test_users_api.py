import pytest

pytestmark = pytest.mark.asyncio

API = "/api/v1/users"


def new_user(email="new@test.com", **kw):
    base = {"email": email, "password": "Password123!", "full_name": "New Person", "role": "VIEWER"}
    base.update(kw)
    return base


async def me(client, headers):
    return (await client.get("/api/v1/auth/me", headers=headers)).json()["data"]


async def test_only_admins_can_manage_users(client, viewer_headers, marketing_headers, admin_headers):
    assert (await client.get(API)).status_code == 401
    assert (await client.get(API, headers=viewer_headers)).status_code == 403
    assert (await client.get(API, headers=marketing_headers)).status_code == 403
    assert (await client.post(API, json=new_user(), headers=viewer_headers)).status_code == 403
    listing = (await client.get(API, headers=admin_headers)).json()["data"]
    assert listing["total"] == 3 and {u["role"] for u in listing["items"]} == {"VIEWER", "MARKETING_MANAGER", "ADMIN"}
    assert "hashed_password" not in str(listing) and "refresh_token" not in str(listing)


async def test_create_user_and_login(client, admin_headers):
    r = await client.post(API, json=new_user(" New@Test.com ", role="MARKETING_MANAGER"), headers=admin_headers)
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["email"] == "new@test.com" and data["role"] == "MARKETING_MANAGER" and data["is_active"] is True
    login = await client.post("/api/v1/auth/login", json={"email": "new@test.com", "password": "Password123!"})
    assert login.status_code == 200
    dup = await client.post(API, json=new_user("NEW@test.com"), headers=admin_headers)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


@pytest.mark.parametrize("bad", [{"password": "short"}, {"email": "not-an-email"}, {"role": "KING"}, {"full_name": "x" * 300}])
async def test_create_validation(client, admin_headers, bad):
    r = await client.post(API, json=new_user(**bad), headers=admin_headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_only_super_admin_manages_super_admins(client, admin_headers, super_headers):
    # admin cannot create a super admin
    denied = await client.post(API, json=new_user("boss@test.com", role="SUPER_ADMIN"), headers=admin_headers)
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "INSUFFICIENT_ROLE"
    # only one super admin is allowed: since super@test.com already exists, creating a 2nd fails with 409
    dup_super = await client.post(API, json=new_user("boss@test.com", role="SUPER_ADMIN"), headers=super_headers)
    assert dup_super.status_code == 409 and dup_super.json()["error"]["code"] == "ONLY_ONE_SUPER_ADMIN"

    super_id = (await me(client, super_headers))["id"]
    # admin cannot edit super admin's details
    assert (await client.patch(f"{API}/{super_id}", json={"is_active": False}, headers=admin_headers)).status_code == 403
    assert (await client.patch(f"{API}/{super_id}", json={"full_name": "Boss"}, headers=admin_headers)).status_code == 403
    # super admin CAN edit their own details (name, email, password)
    assert (await client.patch(f"{API}/{super_id}", json={"full_name": "Boss", "email": "super_updated@test.com"}, headers=super_headers)).status_code == 200
    # an admin cannot promote someone to super admin either
    victim = (await client.post(API, json=new_user("v@test.com"), headers=admin_headers)).json()["data"]["id"]
    assert (await client.patch(f"{API}/{victim}", json={"role": "SUPER_ADMIN"}, headers=admin_headers)).status_code == 403


async def test_update_fields_and_validation(client, admin_headers):
    uid = (await client.post(API, json=new_user(), headers=admin_headers)).json()["data"]["id"]
    r = await client.patch(f"{API}/{uid}", json={"full_name": "  Renamed  ", "role": "DATA_ANALYST"}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["data"]["full_name"] == "Renamed" and r.json()["data"]["role"] == "DATA_ANALYST"
    assert (await client.patch(f"{API}/{uid}", json={}, headers=admin_headers)).status_code == 422
    assert (await client.patch(f"{API}/{uid}", json={"password": "short"}, headers=admin_headers)).status_code == 422
    assert (await client.patch(f"{API}/{uid}", json={"role": "KING"}, headers=admin_headers)).status_code == 422
    missing = await client.patch(f"{API}/00000000-0000-0000-0000-000000000000", json={"full_name": "x"}, headers=admin_headers)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "USER_NOT_FOUND"
    assert (await client.patch(f"{API}/not-a-uuid", json={"full_name": "x"}, headers=admin_headers)).status_code == 422


async def test_deactivation_blocks_login_and_existing_tokens(client, admin_headers):
    uid = (await client.post(API, json=new_user("temp@test.com", role="ADMIN"), headers=admin_headers)).json()["data"]["id"]
    tokens = (await client.post("/api/v1/auth/login", json={"email": "temp@test.com", "password": "Password123!"})).json()["data"]
    bearer = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert (await client.get("/api/v1/auth/me", headers=bearer)).status_code == 200

    assert (await client.patch(f"{API}/{uid}", json={"is_active": False}, headers=admin_headers)).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=bearer)).status_code == 401                     # token stops working at once
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})).status_code == 401
    assert (await client.post("/api/v1/auth/login", json={"email": "temp@test.com", "password": "Password123!"})).status_code == 401

    assert (await client.patch(f"{API}/{uid}", json={"is_active": True}, headers=admin_headers)).status_code == 200
    assert (await client.post("/api/v1/auth/login", json={"email": "temp@test.com", "password": "Password123!"})).status_code == 200


async def test_password_reset_invalidates_sessions(client, admin_headers):
    uid = (await client.post(API, json=new_user("pw@test.com"), headers=admin_headers)).json()["data"]["id"]
    tokens = (await client.post("/api/v1/auth/login", json={"email": "pw@test.com", "password": "Password123!"})).json()["data"]
    await client.patch(f"{API}/{uid}", json={"password": "Brand-new-pass1"}, headers=admin_headers)
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})).status_code == 401
    assert (await client.post("/api/v1/auth/login", json={"email": "pw@test.com", "password": "Password123!"})).status_code == 401
    assert (await client.post("/api/v1/auth/login", json={"email": "pw@test.com", "password": "Brand-new-pass1"})).status_code == 200


async def test_cannot_lock_yourself_or_the_last_super_admin_out(client, admin_headers, super_headers):
    admin_id, super_id = (await me(client, admin_headers))["id"], (await me(client, super_headers))["id"]
    own_role = await client.patch(f"{API}/{admin_id}", json={"role": "VIEWER"}, headers=admin_headers)
    assert own_role.status_code == 409 and own_role.json()["error"]["code"] == "CANNOT_MODIFY_SELF"
    assert (await client.patch(f"{API}/{admin_id}", json={"is_active": False}, headers=admin_headers)).status_code == 409
    assert (await client.patch(f"{API}/{admin_id}", json={"full_name": "Me", "password": "Another-pass-9"}, headers=admin_headers)).status_code == 200

    # super admin tries to demote themselves -> blocked as self-modification
    assert (await client.patch(f"{API}/{super_id}", json={"role": "ADMIN"}, headers=super_headers)).status_code == 409


async def test_delete_user_rules(client, admin_headers, super_headers):
    super_id = (await me(client, super_headers))["id"]
    admin_id = (await me(client, admin_headers))["id"]

    # 1. Super Admin cannot be deleted by anyone
    del_super_by_admin = await client.delete(f"{API}/{super_id}", headers=admin_headers)
    assert del_super_by_admin.status_code == 409 and del_super_by_admin.json()["error"]["code"] == "CANNOT_DELETE_SUPER_ADMIN"
    del_super_by_super = await client.delete(f"{API}/{super_id}", headers=super_headers)
    assert del_super_by_super.status_code == 409 and del_super_by_super.json()["error"]["code"] == "CANNOT_DELETE_SUPER_ADMIN"

    # 2. Cannot delete yourself
    del_self = await client.delete(f"{API}/{admin_id}", headers=admin_headers)
    assert del_self.status_code == 409 and del_self.json()["error"]["code"] == "CANNOT_DELETE_SELF"

    # 3. Super Admin can delete other staff users (admin, manager, analyst, viewer)
    created = (await client.post(API, json=new_user("todelete@test.com", role="MARKETING_MANAGER"), headers=super_headers)).json()["data"]["id"]
    del_ok = await client.delete(f"{API}/{created}", headers=super_headers)
    assert del_ok.status_code == 200 and del_ok.json()["data"]["deleted"] is True

    # 4. Admin can also delete non-super-admin staff users
    created_by_admin = (await client.post(API, json=new_user("delbyadmin@test.com", role="VIEWER"), headers=admin_headers)).json()["data"]["id"]
    del_by_admin_ok = await client.delete(f"{API}/{created_by_admin}", headers=admin_headers)
    assert del_by_admin_ok.status_code == 200 and del_by_admin_ok.json()["data"]["deleted"] is True
