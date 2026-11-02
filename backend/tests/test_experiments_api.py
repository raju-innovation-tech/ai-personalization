import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

pytestmark = pytest.mark.asyncio

API = "/api/v1/experiments"


def reco_body(key="reco-test", **kw):
    base = {
        "key": key, "name": f"Test {key}", "kind": "recommendations", "traffic_percent": 100,
        "variants": [{"name": "Hybrid", "config": {"strategy": "hybrid"}}, {"name": "Popular", "config": {"strategy": "popular"}}],
    }
    base.update(kw)
    return base


def offers_body(key="offer-test", variants=None, **kw):
    base = {
        "key": key, "name": f"Test {key}", "kind": "offers", "traffic_percent": 100,
        "variants": variants or [{"name": "All offers", "config": {}}, {"name": "Holdout", "config": {"offer_codes": []}}],
    }
    base.update(kw)
    return base


def two_variants(strategy="content"):
    return [{"key": "control", "name": "Control"}, {"key": "b", "name": "Variant B", "config": {"strategy": strategy}}]


async def create(client, headers, body, start=False):
    r = await client.post(API, json=body, headers=headers)
    assert r.status_code == 201, r.text
    exp = r.json()["data"]
    if start:
        s = await client.post(f"{API}/{exp['id']}/status", json={"status": "running"}, headers=headers)
        assert s.status_code == 200, s.text
        exp = s.json()["data"]
    return exp


async def set_status(client, headers, exp, status, **kw):
    return await client.post(f"{API}/{exp['id']}/status", json={"status": status, **kw}, headers=headers)


# ------------------------------------------------------------------ permissions
async def test_permissions(client, viewer_headers, marketing_headers, admin_headers):
    assert (await client.get(API)).status_code == 401
    assert (await client.get(f"{API}/stats")).status_code == 401
    assert (await client.get(API, headers=viewer_headers)).status_code == 200
    assert (await client.post(API, json=reco_body(), headers=viewer_headers)).status_code == 403
    assert (await client.post(API, json=reco_body("mkt-test"), headers=marketing_headers)).status_code == 201
    assert (await client.post(API, json=reco_body("adm-test"), headers=admin_headers)).status_code == 201


# ------------------------------------------------------------------- validation
@pytest.mark.parametrize(
    "mutation",
    [
        {"key": "ab"},                                                               # too short
        {"key": "Bad Key!"},
        {"kind": "emails"},
        {"primary_metric": "vibes"},
        {"traffic_percent": 0},
        {"traffic_percent": 101},
        {"variants": [{"name": "only one"}]},                                        # needs two
        {"variants": [{"name": f"v{i}"} for i in range(6)]},                         # at most five
        {"variants": [{"name": "A", "key": "x"}, {"name": "B", "key": "x"}]},        # duplicate keys
        {"variants": [{"name": "A", "weight": 0}, {"name": "B"}]},                   # weight must be > 0
        {"variants": [{"name": "A", "config": {"strategy": "magic"}}, {"name": "B"}]},
        {"variants": [{"name": "  "}, {"name": "B"}]},
        {"variants": [{"name": "A", "key": "Bad Key"}, {"name": "B"}]},
    ],
)
async def test_create_validation(client, admin_headers, mutation):
    r = await client.post(API, json=reco_body(**mutation), headers=admin_headers)
    assert r.status_code == 422, mutation
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_offer_config_validation(client, admin_headers):
    bad_codes = offers_body(variants=[{"name": "A"}, {"name": "B", "config": {"offer_codes": ["bad code!"]}}])
    assert (await client.post(API, json=bad_codes, headers=admin_headers)).status_code == 422
    not_list = offers_body(variants=[{"name": "A"}, {"name": "B", "config": {"offer_codes": "VIP15"}}])
    assert (await client.post(API, json=not_list, headers=admin_headers)).status_code == 422


async def test_single_letter_variant_keys_are_allowed(client, admin_headers):
    exp = await create(client, admin_headers, reco_body("letters", variants=[{"key": "a", "name": "A"}, {"key": "b", "name": "B"}]))
    assert [v["key"] for v in exp["variants"]] == ["a", "b"]


async def test_create_normalises_keys_and_config(client, admin_headers):
    exp = await create(client, admin_headers, reco_body(" Reco-Norm ", variants=[
        {"name": "Current"}, {"name": "Content Based!", "config": {"strategy": "content", "junk": 1}}]))
    assert exp["key"] == "reco-norm" and exp["status"] == "draft"
    assert [v["key"] for v in exp["variants"]] == ["control", "content-based"]
    assert exp["variants"][0]["is_control"] is True and exp["variants"][1]["is_control"] is False
    assert exp["variants"][0]["config"] == {"strategy": "hybrid"} and exp["variants"][1]["config"] == {"strategy": "content"}
    assert [v["share"] for v in exp["variants"]] == [0.5, 0.5]

    offers = await create(client, admin_headers, offers_body(variants=[
        {"name": "All"}, {"name": "Two", "weight": 3, "config": {"offer_codes": ["vip15", " VIP15", "welcome10"]}}]))
    assert offers["variants"][1]["config"] == {"offer_codes": ["VIP15", "WELCOME10"]} and offers["variants"][1]["share"] == 0.75
    assert offers["variants"][0]["config"] == {}

    dup = await client.post(API, json=reco_body("reco-norm"), headers=admin_headers)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "EXPERIMENT_KEY_EXISTS"


# --------------------------------------------------------------------- lifecycle
async def test_lifecycle_transitions(client, admin_headers):
    exp = await create(client, admin_headers, reco_body("life"))
    assert (await set_status(client, admin_headers, exp, "paused")).status_code == 409       # draft cannot pause
    assert (await set_status(client, admin_headers, exp, "completed")).status_code == 409    # nor complete
    started = (await set_status(client, admin_headers, exp, "running")).json()["data"]
    assert started["status"] == "running" and started["started_at"]
    assert (await set_status(client, admin_headers, exp, "paused")).json()["data"]["status"] == "paused"
    resumed = (await set_status(client, admin_headers, exp, "running")).json()["data"]
    assert resumed["started_at"] == started["started_at"]                                    # first start time is kept
    unknown = await set_status(client, admin_headers, exp, "completed", winner_key="nope")
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "UNKNOWN_VARIANT"
    done = (await set_status(client, admin_headers, exp, "completed", winner_key="popular")).json()["data"]
    assert done["status"] == "completed" and done["winner_key"] == "popular" and done["ended_at"]
    final = await set_status(client, admin_headers, exp, "running")
    assert final.status_code == 409 and final.json()["error"]["code"] == "INVALID_TRANSITION"
    assert (await set_status(client, admin_headers, exp, "completed")).status_code == 200      # same status is a no-op


async def test_one_running_experiment_per_surface(client, admin_headers):
    first = await create(client, admin_headers, reco_body("first"), start=True)
    second = await create(client, admin_headers, reco_body("second"))
    busy = await set_status(client, admin_headers, second, "running")
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "EXPERIMENT_KIND_BUSY" and "first" in busy.json()["error"]["message"]
    offers = await create(client, admin_headers, offers_body("other-surface"))
    assert (await set_status(client, admin_headers, offers, "running")).status_code == 200      # a different surface is fine
    await set_status(client, admin_headers, first, "paused")
    assert (await set_status(client, admin_headers, second, "running")).status_code == 200      # frees up when paused


async def test_starting_an_offer_test_checks_the_offer_codes(client, admin_headers):
    exp = await create(client, admin_headers, offers_body("needs-offer", variants=[{"name": "A"}, {"name": "B", "config": {"offer_codes": ["GHOST10"]}}]))
    r = await set_status(client, admin_headers, exp, "running")
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNKNOWN_OFFER_CODE" and "GHOST10" in r.json()["error"]["message"]
    await client.post("/api/v1/offers", json={"code": "GHOST10", "name": "Ghost", "offer_type": "percent_off", "value": 10}, headers=admin_headers)
    assert (await set_status(client, admin_headers, exp, "running")).status_code == 200


async def test_only_drafts_can_be_edited(client, admin_headers):
    exp = await create(client, admin_headers, reco_body("edit-me"))
    ok = await client.put(f"{API}/{exp['id']}", json=reco_body("edit-me", name="Renamed", traffic_percent=40), headers=admin_headers)
    assert ok.status_code == 200 and ok.json()["data"]["name"] == "Renamed" and ok.json()["data"]["traffic_percent"] == 40
    renamed_key = await client.put(f"{API}/{exp['id']}", json=reco_body("other-key"), headers=admin_headers)
    assert renamed_key.status_code == 422 and renamed_key.json()["error"]["code"] == "KEY_IMMUTABLE"
    await set_status(client, admin_headers, exp, "running")
    live = await client.put(f"{API}/{exp['id']}", json=reco_body("edit-me"), headers=admin_headers)
    assert live.status_code == 409 and live.json()["error"]["code"] == "EXPERIMENT_NOT_DRAFT"


async def test_get_list_and_not_found(client, admin_headers):
    a = await create(client, admin_headers, reco_body("alpha-test"))
    await create(client, admin_headers, offers_body("beta-test"), start=True)
    assert (await client.get(f"{API}/{a['id']}", headers=admin_headers)).json()["data"]["key"] == "alpha-test"
    missing = await client.get(f"{API}/{uuid.uuid4()}", headers=admin_headers)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "EXPERIMENT_NOT_FOUND"
    assert (await client.get(f"{API}/{uuid.uuid4()}/results", headers=admin_headers)).status_code == 404
    assert (await client.get(f"{API}/not-a-uuid", headers=admin_headers)).status_code == 422

    listing = (await client.get(API, headers=admin_headers)).json()["data"]
    assert listing["total"] == 2
    assert (await client.get(f"{API}?status=running", headers=admin_headers)).json()["data"]["items"][0]["key"] == "beta-test"
    assert (await client.get(f"{API}?kind=recommendations", headers=admin_headers)).json()["data"]["total"] == 1
    assert (await client.get(f"{API}?q=ALPHA", headers=admin_headers)).json()["data"]["total"] == 1
    assert (await client.get(f"{API}?status=bogus", headers=admin_headers)).status_code == 422
    stats = (await client.get(f"{API}/stats", headers=admin_headers)).json()["data"]
    assert stats["total"] == 2 and stats["by_status"]["running"] == 1 and stats["running"][0]["key"] == "beta-test"


# --------------------------------------------------------- serving integration
async def seed_history(client, admin_headers, users):
    await client.post("/api/v1/products/bulk", json={"products": [
        {"product_id": f"P{i}", "name": f"Product {i}", "category": "Laptops" if i % 2 else "Phones", "price": 100} for i in range(1, 7)]},
        headers=admin_headers)
    events = [{"event_type": "PRODUCT_VIEW", "external_user_id": u, "product_id": f"P{1 + i % 3}", "timestamp": datetime.now(timezone.utc).isoformat()}
              for i, u in enumerate(users)]
    assert (await client.post("/api/v1/events/batch", json={"events": events})).status_code == 201


async def test_recommendation_experiment_changes_the_strategy_and_records_exposure(client, admin_headers):
    users = [f"user{i}" for i in range(40)]
    await seed_history(client, admin_headers, users)
    exp = await create(client, admin_headers, reco_body("serve-reco"), start=True)

    served = {}
    for u in users:
        data = (await client.get(f"/api/v1/recommendations/user/{u}?limit=3")).json()["data"]
        served[u] = data
        assert data["experiment"]["key"] == "serve-reco" and data["experiment"]["id"] == exp["id"]
    variants = {u: d["experiment"]["variant"] for u, d in served.items()}
    assert set(variants.values()) == {"control", "popular"}
    for u, d in served.items():
        if variants[u] == "popular":
            assert d["algorithm"] == "popular" and d["personalized"] is False
        else:
            assert d["algorithm"] == "hybrid" and d["personalized"] is True

    again = (await client.get(f"/api/v1/recommendations/user/{users[0]}?limit=3")).json()["data"]
    assert again["experiment"]["variant"] == variants[users[0]]                      # sticky
    detail = (await client.get(f"{API}/{exp['id']}", headers=admin_headers)).json()["data"]
    assert detail["exposed_total"] == 40                                             # one exposure per customer, repeats not counted
    assert sum(v["exposed"] for v in detail["variants"]) == 40 and all(v["exposed"] > 5 for v in detail["variants"])

    preview = (await client.get(f"{API}/{exp['id']}/assign/{users[1]}", headers=admin_headers)).json()["data"]
    assert preview["variant"] == variants[users[1]] and preview["already_exposed"] is True
    fresh = (await client.get(f"{API}/{exp['id']}/assign/brand-new", headers=admin_headers)).json()["data"]
    assert fresh["already_exposed"] is False and fresh["first_exposed_at"] is None
    assert (await client.get(f"{API}/{exp['id']}", headers=admin_headers)).json()["data"]["exposed_total"] == 40   # preview records nothing


async def test_no_experiment_means_normal_behaviour_and_paused_stops_assigning(client, admin_headers):
    await seed_history(client, admin_headers, ["u1"])
    plain = (await client.get("/api/v1/recommendations/user/u1")).json()["data"]
    assert plain["experiment"] is None and plain["algorithm"] == "hybrid"

    exp = await create(client, admin_headers, reco_body("pause-me"), start=True)
    await client.get("/api/v1/recommendations/user/u1")
    await set_status(client, admin_headers, exp, "paused")
    assert (await client.get("/api/v1/recommendations/user/u2")).json()["data"]["experiment"] is None
    assert (await client.get(f"{API}/{exp['id']}", headers=admin_headers)).json()["data"]["exposed_total"] <= 1
    await set_status(client, admin_headers, exp, "completed")
    assert (await client.get("/api/v1/recommendations/user/u3")).json()["data"]["experiment"] is None


async def test_traffic_percent_limits_who_takes_part(client, admin_headers):
    await create(client, admin_headers, reco_body("small", traffic_percent=10), start=True)
    flags = [(await client.get(f"/api/v1/recommendations/user/visitor{i}")).json()["data"]["experiment"] is not None for i in range(120)]
    assert 2 <= sum(flags) <= 30                                                      # ~10 % of 120


async def test_offer_experiment_holdout(client, admin_headers):
    for code in ("AAA10", "BBB10"):
        o = (await client.post("/api/v1/offers", json={"code": code, "name": code, "offer_type": "percent_off", "value": 10}, headers=admin_headers)).json()["data"]
        await client.post(f"/api/v1/offers/{o['id']}/status", json={"status": "active"}, headers=admin_headers)
    exp = await create(client, admin_headers, offers_body("holdout", variants=[
        {"name": "All offers"}, {"name": "Holdout", "config": {"offer_codes": []}}, {"name": "Only A", "config": {"offer_codes": ["aaa10"]}}]), start=True)
    seen = {}
    for i in range(60):
        data = (await client.get(f"/api/v1/offers/user/shopper{i}")).json()["data"]
        seen.setdefault(data["experiment"]["variant"], set()).add(tuple(sorted(o["code"] for o in data["items"])))
    assert seen["control"] == {("AAA10", "BBB10")}
    assert seen["holdout"] == {()}
    assert seen["only-a"] == {("AAA10",)}
    assert (await client.get(f"{API}/{exp['id']}", headers=admin_headers)).json()["data"]["exposed_total"] == 60


# ------------------------------------------------------------------------ results
async def add_exposures_and_outcomes(db_session, experiment_id, *, per_variant, control_buyers, variant_buyers, exposed_days_ago=3):
    """Direct DB inserts so the numbers are exact: purchases of a 100-priced product after exposure."""
    from app.database.models.event import EventType, Platform, UserEvent
    from app.database.models.experiment import ExperimentExposure

    exposed_at = datetime.now(timezone.utc) - timedelta(days=exposed_days_ago)
    n = 0
    for variant, buyers in (("control", control_buyers), ("b", variant_buyers)):
        for i in range(per_variant):
            user = f"{variant}-{i}"
            db_session.add(ExperimentExposure(experiment_id=uuid.UUID(experiment_id), external_user_id=user, variant_key=variant, first_exposed_at=exposed_at))
            if i < buyers:
                n += 1
                db_session.add(UserEvent(external_user_id=user, event_type=EventType.PURCHASE, product_id="P1", session_id=f"s{n}",
                                         platform=Platform.WEB, event_metadata={}, occurred_at=exposed_at + timedelta(days=1), idempotency_key=f"k{n}-{experiment_id}"))
    await db_session.commit()


async def test_results_math_and_verdict(client, admin_headers, db_session):
    await client.post("/api/v1/products", json={"product_id": "P1", "name": "One", "price": 100}, headers=admin_headers)
    exp = await create(client, admin_headers, reco_body("results", variants=[
        {"key": "control", "name": "Control", "config": {"strategy": "hybrid"}}, {"key": "b", "name": "Variant B", "config": {"strategy": "content"}}]), start=True)
    await add_exposures_and_outcomes(db_session, exp["id"], per_variant=100, control_buyers=10, variant_buyers=30)

    r = (await client.get(f"{API}/{exp['id']}/results", headers=admin_headers)).json()["data"]
    control, b = r["variants"]
    assert (control["customers"], control["conversions"], control["conversion_rate"]) == (100, 10, 0.1)
    assert (b["customers"], b["conversions"], b["conversion_rate"]) == (100, 30, 0.3)
    assert control["revenue_per_customer"] == 10.0 and b["revenue_per_customer"] == 30.0 and b["revenue_total"] == 3000.0
    assert control["comparisons"] is None
    conv = b["comparisons"]["conversion"]
    assert conv["significant"] is True and conv["p_value"] < 0.01 and conv["lift"] == 2.0 and conv["diff"] == 0.2
    assert b["comparisons"]["revenue"]["significant"] is True
    assert r["verdict"]["status"] == "winner" and r["verdict"]["winner_key"] == "b" and "Variant B" in r["verdict"]["message"]


async def test_results_only_count_outcomes_inside_the_window(client, admin_headers, db_session):
    from app.database.models.event import EventType, Platform, UserEvent

    await client.post("/api/v1/products", json={"product_id": "P1", "name": "One", "price": 100}, headers=admin_headers)
    exp = await create(client, admin_headers, reco_body("window", variants=two_variants()), start=True)
    await add_exposures_and_outcomes(db_session, exp["id"], per_variant=40, control_buyers=0, variant_buyers=0)
    now = datetime.now(timezone.utc)
    db_session.add(UserEvent(external_user_id="control-0", event_type=EventType.PURCHASE, product_id="P1", session_id="before", platform=Platform.WEB,
                             event_metadata={}, occurred_at=now - timedelta(days=10), idempotency_key="before-exposure"))    # before exposure
    await db_session.commit()
    assert (await client.get(f"{API}/{exp['id']}/results", headers=admin_headers)).json()["data"]["variants"][0]["conversions"] == 0

    await set_status(client, admin_headers, exp, "completed")
    db_session.add(UserEvent(external_user_id="control-1", event_type=EventType.PURCHASE, product_id="P1", session_id="after", platform=Platform.WEB,
                             event_metadata={}, occurred_at=now + timedelta(minutes=5), idempotency_key="after-the-end"))      # after the test ended
    await db_session.commit()
    done = (await client.get(f"{API}/{exp['id']}/results", headers=admin_headers)).json()["data"]
    assert done["variants"][0]["conversions"] == 0 and done["verdict"]["status"] == "inconclusive"


async def test_results_collecting_and_recommendation_clicks(client, admin_headers, db_session):
    from app.database.models.event import EventType, Platform, UserEvent

    exp = await create(client, admin_headers, reco_body("few", primary_metric="click", variants=two_variants()), start=True)
    await add_exposures_and_outcomes(db_session, exp["id"], per_variant=8, control_buyers=0, variant_buyers=0)
    exposed = datetime.now(timezone.utc) - timedelta(days=2)
    for i in range(3):
        db_session.add(UserEvent(external_user_id=f"b-{i}", event_type=EventType.RECOMMENDATION_CLICK, product_id=None, session_id="c",
                                 platform=Platform.WEB, event_metadata={}, occurred_at=exposed + timedelta(hours=2), idempotency_key=f"click-{i}"))
    await db_session.commit()
    r = (await client.get(f"{API}/{exp['id']}/results", headers=admin_headers)).json()["data"]
    assert r["verdict"]["status"] == "collecting" and r["sample"]["smallest_variant"] == 8
    assert r["variants"][1]["clickers"] == 3 and r["variants"][1]["click_rate"] == 0.375 and r["variants"][0]["clickers"] == 0


async def test_offer_experiment_clicks_come_from_offer_interactions(client, admin_headers, db_session):
    from app.database.models.offer import OfferInteraction

    o = (await client.post("/api/v1/offers", json={"code": "CLK10", "name": "Click", "offer_type": "percent_off", "value": 10}, headers=admin_headers)).json()["data"]
    exp = await create(client, admin_headers, offers_body("offer-clicks", primary_metric="click", variants=[
        {"key": "control", "name": "All"}, {"key": "b", "name": "B", "config": {"offer_codes": []}}]), start=True)
    await add_exposures_and_outcomes(db_session, exp["id"], per_variant=5, control_buyers=0, variant_buyers=0)
    for i in range(2):
        db_session.add(OfferInteraction(offer_id=uuid.UUID(o["id"]), external_user_id=f"control-{i}", action="click",
                                        occurred_at=datetime.now(timezone.utc) - timedelta(days=1)))
    db_session.add(OfferInteraction(offer_id=uuid.UUID(o["id"]), external_user_id="control-4", action="impression", occurred_at=datetime.now(timezone.utc) - timedelta(days=1)))
    await db_session.commit()
    r = (await client.get(f"{API}/{exp['id']}/results", headers=admin_headers)).json()["data"]
    assert r["variants"][0]["clickers"] == 2                                          # impressions do not count as clicks


# ------------------------------------------------------------------------- alerts
async def test_alerts_for_idle_and_decided_experiments(client, admin_headers, viewer_headers, db_session):
    from app.database.models.experiment import Experiment

    await client.post("/api/v1/products", json={"product_id": "P1", "name": "One", "price": 100}, headers=admin_headers)
    idle = await create(client, admin_headers, offers_body("idle-test"), start=True)
    await db_session.execute(update(Experiment).where(Experiment.key == "idle-test").values(started_at=datetime.now(timezone.utc) - timedelta(days=2)))
    await db_session.commit()
    items = {a["id"]: a for a in (await client.get("/api/v1/system/alerts", headers=viewer_headers)).json()["data"]["items"]}
    assert items["experiment_idle_idle-test"]["severity"] == "warning" and items["experiment_idle_idle-test"]["link"] == "/experiments"

    await set_status(client, admin_headers, idle, "completed")
    reco = await create(client, admin_headers, reco_body("decided", variants=two_variants()), start=True)
    await add_exposures_and_outcomes(db_session, reco["id"], per_variant=100, control_buyers=10, variant_buyers=40)
    items = {a["id"]: a for a in (await client.get("/api/v1/system/alerts", headers=viewer_headers)).json()["data"]["items"]}
    assert items["experiment_result_decided"]["severity"] == "info" and "beats the control" in items["experiment_result_decided"]["message"]
    assert "experiment_idle_idle-test" not in items


async def test_concurrent_first_requests_record_one_exposure(client, admin_headers):
    exp = await create(client, admin_headers, reco_body("race"), start=True)
    responses = await asyncio.gather(*[client.get("/api/v1/recommendations/user/same-user") for _ in range(8)])
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()["data"]["experiment"]["variant"] for r in responses}) == 1
    assert (await client.get(f"{API}/{exp['id']}", headers=admin_headers)).json()["data"]["exposed_total"] == 1
