import asyncio
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio

API = "/api/v1/offers"


def iso(days=0.0):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def body(code="SAVE10", **kw):
    base = {"code": code, "name": f"Offer {code}", "offer_type": "percent_off", "value": 10}
    base.update(kw)
    return base


async def create(client, headers, code="SAVE10", activate=True, **kw):
    r = await client.post(API, json=body(code, **kw), headers=headers)
    assert r.status_code == 201, r.text
    offer = r.json()["data"]
    if activate:
        s = await client.post(f"{API}/{offer['id']}/status", json={"status": "active"}, headers=headers)
        assert s.status_code == 200, s.text
        offer = s.json()["data"]
    return offer


async def add_customer(db_session, user_id, segment=None, favorite=None):
    from app.database.models.customer import EcommerceCustomer

    db_session.add(EcommerceCustomer(external_user_id=user_id, segment=segment, favorite_category=favorite))
    await db_session.commit()


def checkout(code, user="u1", value=1000, **kw):
    return {"code": code, "external_user_id": user, "order_value": value, **kw}


# ------------------------------------------------------------------ permissions
async def test_permissions(client, viewer_headers, marketing_headers, admin_headers):
    assert (await client.post(API, json=body())).status_code == 401
    assert (await client.post(API, json=body(), headers=viewer_headers)).status_code == 403
    assert (await client.post(API, json=body("MKT10"), headers=marketing_headers)).status_code == 201
    assert (await client.post(API, json=body("ADM10"), headers=admin_headers)).status_code == 201

    for path in ("", "/stats"):
        assert (await client.get(f"{API}{path}")).status_code == 401
        assert (await client.get(f"{API}{path}", headers=viewer_headers)).status_code == 200      # read-only roles may look
    assert (await client.post(f"{API}/validate", json=checkout("X"))).status_code == 401
    assert (await client.post(f"{API}/validate", json=checkout("X"), headers=viewer_headers)).status_code == 403
    assert (await client.post(f"{API}/redeem", json=checkout("X", order_id="o"), headers=viewer_headers)).status_code == 403
    # the storefront-facing endpoints stay open like /events
    assert (await client.get(f"{API}/user/anyone")).status_code == 200


# --------------------------------------------------------------------- validation
@pytest.mark.parametrize(
    "bad",
    [
        {"code": "ab"},                                           # too short
        {"code": "BAD CODE!"},                                    # illegal characters
        {"value": 150},                                           # percent > 100
        {"value": 0},                                             # percent must be > 0
        {"offer_type": "fixed_off", "value": 0},
        {"offer_type": "bogus"},
        {"starts_at": iso(5), "ends_at": iso(1)},                 # ends before it starts
        {"target_segments": ["not_a_segment"]},
        {"starts_at": "2026-10-01T10:00:00"},                     # no timezone
        {"max_per_customer": 0},
        {"max_redemptions": 0},
        {"priority": 101},
        {"name": "   "},
        {"max_discount": -5},
    ],
)
async def test_create_validation(client, admin_headers, bad):
    r = await client.post(API, json=body(**bad), headers=admin_headers)
    assert r.status_code == 422, bad
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_create_normalises_and_rejects_duplicates(client, admin_headers):
    r = await client.post(API, json=body(" summer-1 ", target_segments=["champions", "champions"],
                                         target_categories=[" Laptops ", "Laptops", ""]), headers=admin_headers)
    data = r.json()["data"]
    assert data["code"] == "SUMMER-1" and data["status"] == "draft"
    assert data["target_segments"] == ["champions"] and data["target_categories"] == ["Laptops"]
    dup = await client.post(API, json=body("summer-1"), headers=admin_headers)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "CODE_ALREADY_EXISTS"
    free = await client.post(API, json=body("SHIP", offer_type="free_shipping", value=77), headers=admin_headers)
    assert free.json()["data"]["value"] == 0                       # value is ignored for free shipping


# ---------------------------------------------------------------------- lifecycle
async def test_lifecycle_and_transitions(client, admin_headers):
    offer = await create(client, admin_headers, "LIFE", activate=False)
    oid = offer["id"]
    assert (await client.get(f"{API}/user/u1", headers=admin_headers)).json()["data"]["count"] == 0   # draft is hidden

    async def move(status):
        return await client.post(f"{API}/{oid}/status", json={"status": status}, headers=admin_headers)

    assert (await move("active")).json()["data"]["effective_status"] == "active"
    assert (await client.get(f"{API}/user/u1")).json()["data"]["count"] == 1
    assert (await move("paused")).json()["data"]["status"] == "paused"
    assert (await client.get(f"{API}/user/u1")).json()["data"]["count"] == 0
    assert (await move("active")).status_code == 200
    bad = await move("draft")
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "INVALID_TRANSITION"
    assert (await move("ended")).status_code == 200
    assert (await move("active")).status_code == 409                # ended is final
    assert (await move("ended")).status_code == 200                  # same status is a no-op


async def test_cannot_activate_an_expired_offer(client, admin_headers):
    r = await client.post(API, json=body("PAST", starts_at=iso(-10), ends_at=iso(-1)), headers=admin_headers)
    oid = r.json()["data"]["id"]
    act = await client.post(f"{API}/{oid}/status", json={"status": "active"}, headers=admin_headers)
    assert act.status_code == 422 and act.json()["error"]["code"] == "OFFER_ALREADY_EXPIRED"


async def test_update_rules(client, admin_headers):
    offer = await create(client, admin_headers, "EDIT", activate=False)
    changed = await client.put(f"{API}/{offer['id']}", json=body("EDIT", name="New name", value=25, priority=90), headers=admin_headers)
    assert changed.status_code == 200
    assert changed.json()["data"]["name"] == "New name" and changed.json()["data"]["value"] == 25
    renamed = await client.put(f"{API}/{offer['id']}", json=body("OTHER"), headers=admin_headers)
    assert renamed.status_code == 422 and renamed.json()["error"]["code"] == "CODE_IMMUTABLE"
    await client.post(f"{API}/{offer['id']}/status", json={"status": "ended"}, headers=admin_headers)
    ended = await client.put(f"{API}/{offer['id']}", json=body("EDIT"), headers=admin_headers)
    assert ended.status_code == 409 and ended.json()["error"]["code"] == "OFFER_ENDED"
    missing = await client.get(f"{API}/00000000-0000-0000-0000-000000000000", headers=admin_headers)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "OFFER_NOT_FOUND"
    assert (await client.get(f"{API}/not-a-uuid", headers=admin_headers)).status_code == 422


async def test_expiry_is_derived_from_the_schedule(client, admin_headers, db_session):
    from sqlalchemy import update

    from app.database.models.offer import Offer

    offer = await create(client, admin_headers, "TICK")
    await db_session.execute(update(Offer).where(Offer.code == "TICK").values(ends_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
    await db_session.commit()
    assert (await client.get(f"{API}/user/u1")).json()["data"]["count"] == 0
    shown = (await client.get(f"{API}/{offer['id']}", headers=admin_headers)).json()["data"]
    assert shown["status"] == "active" and shown["effective_status"] == "expired"
    verdict = (await client.post(f"{API}/validate", json=checkout("TICK"), headers=admin_headers)).json()["data"]
    assert verdict["valid"] is False and verdict["reason_code"] == "EXPIRED"


async def test_list_filter_search_sort_paginate(client, admin_headers):
    await create(client, admin_headers, "AAA1", name="Alpha deal", priority=10)
    await create(client, admin_headers, "BBB2", name="Beta deal", priority=90, activate=False)
    await create(client, admin_headers, "CCC3", name="Gamma", priority=50)
    get = lambda q: client.get(f"{API}?{q}", headers=admin_headers)  # noqa: E731
    assert (await get("")).json()["data"]["total"] == 3
    assert (await get("status=draft")).json()["data"]["items"][0]["code"] == "BBB2"
    assert (await get("q=deal")).json()["data"]["total"] == 2
    assert (await get("q=ccc")).json()["data"]["total"] == 1
    assert [o["code"] for o in (await get("sort=priority")).json()["data"]["items"]] == ["BBB2", "CCC3", "AAA1"]
    assert [o["code"] for o in (await get("sort=name")).json()["data"]["items"]] == ["AAA1", "BBB2", "CCC3"]
    page = (await get("page_size=2&page=2")).json()["data"]
    assert (page["total_pages"], len(page["items"])) == (2, 1)
    assert (await get("status=bogus")).status_code == 422
    assert (await get("page_size=500")).status_code == 422


# ------------------------------------------------------------------------ serving
async def test_serving_targets_segments_and_ranks(client, admin_headers, db_session):
    await add_customer(db_session, "champ", segment="champions", favorite="Laptops")
    await add_customer(db_session, "gone", segment="at_risk")
    await create(client, admin_headers, "OPEN", priority=50)
    await create(client, admin_headers, "VIP", target_segments=["champions"], priority=50)
    await create(client, admin_headers, "WINBACK", target_segments=["at_risk"], priority=50)

    champ = (await client.get(f"{API}/user/champ")).json()["data"]["items"]
    assert [o["code"] for o in champ] == ["VIP", "OPEN"]
    assert champ[0]["reason"] == "Made for Champions" and champ[0]["score"] > champ[1]["score"]
    assert "stats" not in champ[0] and "target_segments" not in champ[0]       # internals are not exposed
    assert [o["code"] for o in (await client.get(f"{API}/user/gone")).json()["data"]["items"]] == ["WINBACK", "OPEN"]
    assert [o["code"] for o in (await client.get(f"{API}/user/stranger")).json()["data"]["items"]] == ["OPEN"]
    assert (await client.get(f"{API}/user/champ?limit=1")).json()["data"]["count"] == 1
    assert (await client.get(f"{API}/user/champ?limit=0")).status_code == 422


async def test_serving_category_and_cart_context(client, admin_headers, db_session):
    await add_customer(db_session, "u1", favorite="Laptops")
    await create(client, admin_headers, "LAP", target_categories=["Laptops"], max_discount=500)
    await create(client, admin_headers, "BIG", min_order_value=5000)
    codes = lambda d: [o["code"] for o in d["data"]["items"]]  # noqa: E731
    assert set(codes((await client.get(f"{API}/user/u1")).json())) == {"LAP", "BIG"}
    assert codes((await client.get(f"{API}/user/u1?category=Shoes")).json()) == ["BIG"]
    assert codes((await client.get(f"{API}/user/u1?cart_value=100")).json()) == ["LAP"]
    preview = (await client.get(f"{API}/user/u1?cart_value=10000&category=Laptops")).json()["data"]["items"]
    lap = next(o for o in preview if o["code"] == "LAP")
    assert lap["discount_preview"] == 500.0 and lap["reason"] == "Matches your interest in Laptops"


# ------------------------------------------------------------- validate and redeem
async def test_validate_results(client, admin_headers, db_session):
    await add_customer(db_session, "u1", segment="champions")
    await create(client, admin_headers, "TEN", value=10, max_discount=80, min_order_value=500)
    await create(client, admin_headers, "SHIP", offer_type="free_shipping")
    await create(client, admin_headers, "ONLYLOST", target_segments=["lost"])
    v = lambda **kw: client.post(f"{API}/validate", json=checkout(**kw), headers=admin_headers)  # noqa: E731

    ok = (await v(code="ten", value=500)).json()["data"]                       # codes are case-insensitive
    assert ok["valid"] and ok["discount_amount"] == 50.0 and ok["final_value"] == 450.0
    capped = (await v(code="TEN", value=5000)).json()["data"]
    assert capped["discount_amount"] == 80.0
    assert (await v(code="TEN", value=100)).json()["data"]["reason_code"] == "MIN_ORDER_NOT_MET"
    ship = (await v(code="SHIP", value=100)).json()["data"]
    assert ship["valid"] and ship["free_shipping"] is True and ship["discount_amount"] == 0.0
    assert (await v(code="ONLYLOST")).json()["data"]["reason_code"] == "NOT_ELIGIBLE"
    unknown = await v(code="NOPE123")
    assert unknown.status_code == 200 and unknown.json()["data"]["reason_code"] == "OFFER_NOT_FOUND"
    nothing = (await client.post(f"{API}/validate", json={"code": "TEN"}, headers=admin_headers)).status_code
    assert nothing == 422


async def test_checkout_category_rules(client, admin_headers):
    await create(client, admin_headers, "LAP", target_categories=["Laptops"])
    v = lambda **kw: client.post(f"{API}/validate", json=checkout("LAP", **kw), headers=admin_headers)  # noqa: E731
    assert (await v(categories=["Shoes"])).json()["data"]["reason_code"] == "CATEGORY_NOT_MATCHED"
    assert (await v()).json()["data"]["reason_code"] == "CATEGORY_NOT_MATCHED"
    assert (await v(categories=["laptops", "Shoes"])).json()["data"]["valid"] is True


async def test_redeem_is_idempotent_and_updates_stats(client, admin_headers):
    offer = await create(client, admin_headers, "TEN", value=10, max_per_customer=5)
    redeem = lambda order: client.post(f"{API}/redeem", json=checkout("TEN", order_id=order, value=2000), headers=admin_headers)  # noqa: E731
    first = (await redeem("ORD-1")).json()["data"]
    assert first["redeemed"] and first["duplicate"] is False and first["discount_amount"] == 200.0
    again = (await redeem("ORD-1")).json()["data"]
    assert again["redeemed"] and again["duplicate"] is True and again["discount_amount"] == 200.0
    assert (await redeem("ORD-2")).json()["data"]["duplicate"] is False
    stats = (await client.get(f"{API}/{offer['id']}", headers=admin_headers)).json()["data"]["stats"]
    assert stats["redemptions"] == 2 and stats["discount_given"] == 400.0 and stats["revenue"] == 4000.0
    missing = (await client.post(f"{API}/redeem", json=checkout("TEN"), headers=admin_headers)).status_code
    assert missing == 422                                                         # order_id is mandatory


async def test_per_customer_and_total_limits(client, admin_headers):
    await create(client, admin_headers, "ONCE", max_per_customer=1)
    await create(client, admin_headers, "TWO", max_redemptions=2, max_per_customer=5)
    redeem = lambda code, user, order: client.post(  # noqa: E731
        f"{API}/redeem", json=checkout(code, user=user, order_id=order), headers=admin_headers)

    assert (await redeem("ONCE", "u1", "a")).json()["data"]["redeemed"] is True
    blocked = (await redeem("ONCE", "u1", "b")).json()["data"]
    assert blocked["redeemed"] is False and blocked["reason_code"] == "CUSTOMER_LIMIT_REACHED"
    assert (await redeem("ONCE", "u2", "c")).json()["data"]["redeemed"] is True

    assert (await redeem("TWO", "u1", "1")).json()["data"]["redeemed"]
    assert (await redeem("TWO", "u2", "2")).json()["data"]["redeemed"]
    full = (await redeem("TWO", "u3", "3")).json()["data"]
    assert full["redeemed"] is False and full["reason_code"] == "LIMIT_REACHED"
    # the order that already redeemed is still reported as redeemed (idempotent), even when the budget is full
    assert (await redeem("TWO", "u1", "1")).json()["data"]["duplicate"] is True
    remaining = (await client.get(f"{API}?q=TWO", headers=admin_headers)).json()["data"]["items"][0]["stats"]["remaining"]
    assert remaining == 0
    # a customer who used up an offer no longer sees it
    assert "ONCE" not in [o["code"] for o in (await client.get(f"{API}/user/u1")).json()["data"]["items"]]


async def test_concurrent_redemptions_never_exceed_the_budget(client, admin_headers):
    offer = await create(client, admin_headers, "RACE", max_redemptions=3)
    responses = await asyncio.gather(*[
        client.post(f"{API}/redeem", json=checkout("RACE", user=f"user{i}", order_id=f"o{i}"), headers=admin_headers)
        for i in range(10)
    ])
    assert all(r.status_code == 200 for r in responses)
    outcomes = [r.json()["data"] for r in responses]
    assert sum(o["redeemed"] for o in outcomes) == 3
    assert {o["reason_code"] for o in outcomes if not o["redeemed"]} == {"LIMIT_REACHED"}
    assert (await client.get(f"{API}/{offer['id']}", headers=admin_headers)).json()["data"]["stats"]["redemptions"] == 3


async def test_concurrent_duplicate_order_redeems_once(client, admin_headers):
    offer = await create(client, admin_headers, "SAMEORDER", max_per_customer=5)
    responses = await asyncio.gather(*[
        client.post(f"{API}/redeem", json=checkout("SAMEORDER", order_id="ONE"), headers=admin_headers) for _ in range(6)
    ])
    assert all(r.status_code == 200 and r.json()["data"]["redeemed"] for r in responses)
    assert sum(not r.json()["data"]["duplicate"] for r in responses) == 1
    assert (await client.get(f"{API}/{offer['id']}", headers=admin_headers)).json()["data"]["stats"]["redemptions"] == 1


# -------------------------------------------------------------------------- track
async def test_tracking_feeds_stats_and_is_idempotent(client, admin_headers):
    offer = await create(client, admin_headers, "TRK")
    track = lambda **kw: client.post(f"{API}/track", json={"code": "trk", "external_user_id": "u1", **kw})  # noqa: E731
    assert (await track(action="impression")).status_code == 201
    assert (await track(action="impression")).status_code == 201
    assert (await track(action="click", idempotency_key="click-key-1")).json()["data"]["status"] == "accepted"
    assert (await track(action="click", idempotency_key="click-key-1")).json()["data"]["status"] == "duplicate"
    assert (await track(action="hover")).status_code == 422
    missing = await client.post(f"{API}/track", json={"code": "NOPE12", "external_user_id": "u", "action": "click"})
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "OFFER_NOT_FOUND"

    s = (await client.get(f"{API}/{offer['id']}", headers=admin_headers)).json()["data"]["stats"]
    assert (s["impressions"], s["clicks"], s["ctr"]) == (2, 1, 0.5)
    # tracking also lands in the customer's behaviour timeline
    await client.post("/api/v1/customers/recompute", headers=admin_headers)
    timeline = (await client.get("/api/v1/customers/u1/timeline", headers=admin_headers)).json()["data"]["items"]
    assert {e["event_type"] for e in timeline} == {"OFFER_VIEW", "OFFER_CLICK"}


async def test_redeem_writes_a_timeline_event(client, admin_headers):
    await create(client, admin_headers, "EVT")
    await client.post(f"{API}/redeem", json=checkout("EVT", order_id="E1"), headers=admin_headers)
    await client.post("/api/v1/customers/recompute", headers=admin_headers)
    timeline = (await client.get("/api/v1/customers/u1/timeline", headers=admin_headers)).json()["data"]["items"]
    assert [e["event_type"] for e in timeline] == ["OFFER_REDEEM"]


# ------------------------------------------------------------------ stats / overview
async def test_stats_and_dashboard_block(client, admin_headers):
    empty = (await client.get(f"{API}/stats", headers=admin_headers)).json()["data"]
    assert empty["offers"] == 0 and empty["all_time"]["ctr"] is None and empty["active_now"] == 0

    await create(client, admin_headers, "LIVE1", value=10)
    await create(client, admin_headers, "LIVE2", activate=False)
    await client.post(f"{API}/track", json={"code": "LIVE1", "external_user_id": "u1", "action": "impression"})
    await client.post(f"{API}/track", json={"code": "LIVE1", "external_user_id": "u1", "action": "click"})
    await client.post(f"{API}/redeem", json=checkout("LIVE1", order_id="x", value=1000), headers=admin_headers)

    d = (await client.get(f"{API}/stats", headers=admin_headers)).json()["data"]
    assert d["offers"] == 2 and d["by_status"]["active"] == 1 and d["by_status"]["draft"] == 1 and d["active_now"] == 1
    assert d["all_time"]["impressions"] == 1 and d["all_time"]["clicks"] == 1 and d["all_time"]["redemptions"] == 1
    assert d["all_time"]["discount_given"] == 100.0 and d["all_time"]["revenue"] == 1000.0
    assert d["all_time"]["redemption_rate"] == 1.0 and d["last_30d"]["redemptions"] == 1

    overview = (await client.get("/api/v1/analytics/overview", headers=admin_headers)).json()["data"]["offers"]
    assert overview == {"active": 1, "impressions": 1, "clicks": 1, "redemptions": 1, "discount_given": 100.0}


async def test_delete_offer_and_expired_filter(client, admin_headers, super_headers, db_session):
    from sqlalchemy import update
    from app.database.models.offer import Offer

    # Create an active offer then update ends_at to the past
    exp_offer = await create(client, admin_headers, "EXP1", activate=True)
    past = datetime.now(timezone.utc) - timedelta(days=2)
    await db_session.execute(update(Offer).where(Offer.code == "EXP1").values(ends_at=past))
    await db_session.commit()

    draft_offer = await create(client, admin_headers, "DFT1", activate=False)

    # Test expired filter
    res_exp = (await client.get(f"{API}?status=expired", headers=admin_headers)).json()["data"]
    assert any(o["code"] == "EXP1" for o in res_exp["items"])
    assert not any(o["code"] == "DFT1" for o in res_exp["items"])

    # 1. Admin CAN delete draft offer
    del_admin_draft = await client.delete(f"{API}/{draft_offer['id']}", headers=admin_headers)
    assert del_admin_draft.status_code == 200

    # 2. Admin CANNOT delete active/expired offer (403 Forbidden - only super admin allowed)
    del_admin_exp = await client.delete(f"{API}/{exp_offer['id']}", headers=admin_headers)
    assert del_admin_exp.status_code == 403

    # 3. Super Admin CAN delete any offer (including active/expired)
    del_exp_super = await client.delete(f"{API}/{exp_offer['id']}", headers=super_headers)
    assert del_exp_super.status_code == 200

    # Ensure deleted offers are gone
    assert (await client.get(f"{API}/{draft_offer['id']}", headers=admin_headers)).status_code == 404
    assert (await client.get(f"{API}/{exp_offer['id']}", headers=admin_headers)).status_code == 404
