"""Welfog sync: paging / resume logic, SQL page builder, state file and the engine client."""
import json
from datetime import datetime

import httpx
import pytest

from app.integrations.welfog import mapping, readers, runner
from app.integrations.welfog.client import EngineClient, EngineError

ORDERS = readers.SOURCES["orders"]
CARTS = readers.SOURCES["carts"]


# ------------------------------------------------------------------------ SQL builder
def test_first_page_has_no_condition_and_orders_by_timestamp_then_id():
    sql, params = readers.build_select(ORDERS, ["id", "updated_at"], None, None, 500)
    assert "WHERE 1 = 1" in sql and "ORDER BY COALESCE(updated_at, created_at), id LIMIT :limit" in sql
    assert params == {"limit": 500}


def test_next_page_is_strictly_after_the_watermark():
    ts = datetime(2026, 10, 22, 17, 55, 22)
    sql, params = readers.build_select(ORDERS, ["id"], ts, 99, 10)
    assert "(COALESCE(updated_at, created_at) > :last_ts OR (COALESCE(updated_at, created_at) = :last_ts AND id > :last_id))" in sql
    assert params == {"limit": 10, "last_ts": ts, "last_id": 99}


def test_insert_only_sources_page_on_id():
    sql, params = readers.build_select(CARTS, ["id"], None, 41, 5)
    assert "WHERE id > :last_id ORDER BY id LIMIT :limit" in sql and params == {"limit": 5, "last_id": 41}


def test_missing_required_columns_are_reported_and_optional_ones_are_picked_when_present():
    base = set(ORDERS.required)
    assert "session_id" not in readers.pick_columns(ORDERS, base)
    assert "session_id" in readers.pick_columns(ORDERS, base | {"session_id", "platform"})
    with pytest.raises(RuntimeError, match="price"):
        readers.pick_columns(ORDERS, base - {"price"})


# --------------------------------------------------------------------------- run_source
def _cart_rows(n):
    return [{"id": i, "user_id": 1, "product_id": 100 + i, "price": 1.0, "quantity": 1,
             "created_at": datetime(2026, 9, 1, 0, 0, i % 60)} for i in range(1, n + 1)]


def _fetcher(rows):
    def fetch(after_ts, after_id, limit):
        return [r for r in rows if r["id"] > (after_id or 0)][:limit]
    return fetch


def test_all_rows_are_read_in_pages_sent_and_the_watermark_saved():
    sent, saved = [], []
    report = runner.run_source(
        spec=CARTS, fetch=_fetcher(_cart_rows(25)), mapper=mapping.map_cart,
        send=lambda items: (sent.append(len(items)) or (len(items), 0, 0)),
        watermark={}, save=saved.append, page_size=10,
    )
    assert report.rows_read == 25 and report.produced == 25 and sent == [10, 10, 5]
    assert report.sent == (25, 0, 0) and saved[-1] == {"ts": None, "id": 25}


def test_a_resumed_run_continues_after_the_saved_watermark():
    got = []
    runner.run_source(
        spec=CARTS, fetch=_fetcher(_cart_rows(12)), mapper=mapping.map_cart,
        send=lambda items: (got.extend(e["idempotency_key"] for e in items) or (len(items), 0, 0)),
        watermark={"ts": None, "id": 10}, save=lambda wm: None, page_size=500,
    )
    assert got == ["welfog:cart:11", "welfog:cart:12"]


def test_a_failed_send_does_not_move_the_watermark():
    saved = []

    def boom(items):
        raise EngineError("engine down")

    with pytest.raises(EngineError):
        runner.run_source(spec=CARTS, fetch=_fetcher(_cart_rows(5)), mapper=mapping.map_cart, send=boom,
                          watermark={}, save=saved.append, page_size=500)
    assert saved == []


def test_dry_run_sends_nothing_and_saves_nothing_but_still_counts():
    saved = []
    report = runner.run_source(spec=CARTS, fetch=_fetcher(_cart_rows(7)), mapper=mapping.map_cart, send=None,
                               watermark={}, save=saved.append, page_size=3)
    assert report.rows_read == 7 and report.produced == 7 and saved == []


def test_max_rows_limits_the_read_and_skips_are_counted():
    rows = _cart_rows(10)
    rows[2]["user_id"] = None  # guest
    report = runner.run_source(spec=CARTS, fetch=_fetcher(rows), mapper=mapping.map_cart, send=None,
                               watermark={}, save=lambda wm: None, page_size=4, max_rows=6)
    assert report.rows_read == 6 and report.produced == 5 and report.skipped["guest_or_no_user"] == 1


def test_order_pages_move_the_timestamp_watermark_and_it_round_trips_through_json(tmp_path):
    rows = [
        {"id": 1, "oid": 1, "user_id": 5, "product_id": 9, "quantity": 1, "price": 10, "sp_price": 10, "payment_status": "paid",
         "delivery_status": "Delivered", "created_at": datetime(2026, 1, 1), "updated_at": datetime(2026, 1, 2, 3, 4, 5)},
    ]
    store = runner.StateStore(str(tmp_path / "state.json"))
    runner.run_source(spec=ORDERS, fetch=lambda ts, rid, limit: rows if ts is None else [], mapper=mapping.map_order,
                      send=lambda items: (len(items), 0, 0), watermark=store.get("orders"),
                      save=lambda wm: store.set("orders", wm), page_size=500)
    reloaded = runner.StateStore(str(tmp_path / "state.json")).get("orders")
    assert reloaded == {"ts": "2026-01-02 03:04:05", "id": 1}
    assert runner._decode_ts(reloaded["ts"]) == datetime(2026, 1, 2, 3, 4, 5)
    assert json.loads((tmp_path / "state.json").read_text())["orders"]["id"] == 1


# ---------------------------------------------------------------------- engine client
def _client(handler):
    return EngineClient("http://engine/api/v1", "svc@x.com", "pw", transport=httpx.MockTransport(handler), sleep=lambda s: None)


def test_events_batch_success_and_422_falls_back_to_one_by_one():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(len(body["events"]))
        if len(body["events"]) > 1:
            return httpx.Response(422, json={})
        ok = body["events"][0]["external_user_id"] != "bad"
        return httpx.Response(201 if ok else 422, json={"data": {"accepted": 1, "duplicates": 0, "rejected": 0}})

    events = [{"external_user_id": "a"}, {"external_user_id": "bad"}, {"external_user_id": "b"}]
    assert _client(handler).post_events(events) == (2, 0, 1)
    assert calls == [3, 1, 1, 1]


def test_server_errors_are_retried():
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(503)
        return httpx.Response(201, json={"data": {"accepted": 1, "duplicates": 0, "rejected": 0}})

    assert _client(handler).post_events([{"external_user_id": "a"}]) == (1, 0, 0)
    assert len(attempts) == 3


def test_products_need_login_and_relogin_on_401():
    seen = []

    def handler(request):
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(200, json={"data": {"access_token": f"t{len(seen)}"}})
        seen.append(request.headers.get("authorization"))
        if len(seen) == 1:
            return httpx.Response(401)
        return httpx.Response(200, json={"data": {"created": 1, "updated": 0, "total": 1}})

    assert _client(handler).upsert_products([{"product_id": "1", "name": "x"}]) == (1, 0, 0)
    assert seen[0] != seen[1] and all(h.startswith("Bearer ") for h in seen)


def test_products_without_credentials_fail_clearly():
    client = EngineClient("http://engine/api/v1", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    with pytest.raises(EngineError, match="AI_ENGINE_EMAIL"):
        client.upsert_products([{"product_id": "1", "name": "x"}])
