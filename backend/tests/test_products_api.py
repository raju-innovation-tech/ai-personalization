import pytest

pytestmark = pytest.mark.asyncio


def product(pid="SKU-1", **kw):
    base = {"product_id": pid, "name": f"Product {pid}", "category": "Laptops", "brand": "Acme", "price": 999.5}
    base.update(kw)
    return base


async def test_write_requires_auth_and_admin_role(client, viewer_headers):
    assert (await client.post("/api/v1/products", json=product())).status_code == 401
    assert (await client.post("/api/v1/products", json=product(), headers=viewer_headers)).status_code == 403


async def test_viewer_can_read_but_list_requires_auth(client, admin_headers, viewer_headers):
    await client.post("/api/v1/products", json=product(), headers=admin_headers)
    assert (await client.get("/api/v1/products")).status_code == 401
    r = await client.get("/api/v1/products", headers=viewer_headers)
    assert r.status_code == 200 and r.json()["data"]["total"] == 1


async def test_upsert_create_then_update(client, admin_headers):
    first = await client.post("/api/v1/products", json=product(), headers=admin_headers)
    assert first.json()["data"]["created"] is True
    second = await client.post("/api/v1/products", json=product(name="Renamed", price=1200, in_stock=False), headers=admin_headers)
    data = second.json()["data"]
    assert data["created"] is False
    assert data["product"]["name"] == "Renamed" and data["product"]["in_stock"] is False and data["product"]["price"] == 1200


async def test_bulk_upsert_counts_and_last_duplicate_wins(client, admin_headers):
    await client.post("/api/v1/products", json=product("A"), headers=admin_headers)
    r = await client.post(
        "/api/v1/products/bulk",
        json={"products": [product("A", name="A2"), product("B"), product("B", name="B-last")]},
        headers=admin_headers,
    )
    assert r.json()["data"] == {"created": 1, "updated": 1, "total": 2}
    b = await client.get("/api/v1/products/B", headers=admin_headers)
    assert b.json()["data"]["name"] == "B-last"


async def test_validation_rejects_bad_payloads(client, admin_headers):
    for bad in (product(price=-1), product(rating=9), product(name="   "), product(tags=["ok", "bad\u0000"])):
        r = await client.post("/api/v1/products", json=bad, headers=admin_headers)
        assert r.status_code == 422, bad


async def test_list_search_filter_sort_paginate(client, admin_headers):
    items = [product(f"P{i:02d}", name=f"Item {i:02d}", category="Laptops" if i % 2 == 0 else "Wallets",
                     brand="Acme" if i < 6 else "Zeta", price=100 + i) for i in range(12)]
    items.append(product("OFF", name="Hidden", is_active=False))
    await client.post("/api/v1/products/bulk", json={"products": items}, headers=admin_headers)

    page = (await client.get("/api/v1/products?page_size=5&page=2", headers=admin_headers)).json()["data"]
    assert (page["total"], page["total_pages"], len(page["items"])) == (12, 3, 5)   # inactive hidden
    assert (await client.get("/api/v1/products?include_inactive=true", headers=admin_headers)).json()["data"]["total"] == 13
    assert (await client.get("/api/v1/products?category=Wallets", headers=admin_headers)).json()["data"]["total"] == 6
    assert (await client.get("/api/v1/products?brand=Zeta&q=item 1", headers=admin_headers)).json()["data"]["total"] == 2
    top = (await client.get("/api/v1/products?sort=price&order=desc&page_size=1", headers=admin_headers)).json()["data"]
    assert top["items"][0]["product_id"] == "P11"
    assert (await client.get("/api/v1/products?page_size=1000", headers=admin_headers)).status_code == 422

    f = (await client.get("/api/v1/products/filters", headers=admin_headers)).json()["data"]
    assert f["categories"] == ["Laptops", "Wallets"] and f["brands"] == ["Acme", "Zeta"]


async def test_get_unknown_product_is_404_envelope(client, admin_headers):
    r = await client.get("/api/v1/products/NOPE", headers=admin_headers)
    assert r.status_code == 404 and r.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
