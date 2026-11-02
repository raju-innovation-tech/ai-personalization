from app.integrations.service import build_checklist


def raw(**overrides):
    data = {
        "events": {"total": 10, "last_24h": 5},
        "catalog": {"products": 3},
        "data_quality": {"purchase_events_30d": 2, "unknown_product_rate": 0.0, "purchases_without_session_rate": 0.0},
        "profiles": {"last_computed_at": "2026-10-01T00:00:00+00:00"},
        "recommendations": {"served_total": 4},
        "checkout": {"redemptions_total": 1},
        "accounts_summary": {"checkout_capable": 2},
    }
    for key, value in overrides.items():
        data[key] = {**data[key], **value}
    return data


def test_checklist_all_green():
    items = build_checklist(raw())
    assert {i["status"] for i in items} == {"ok"} and len(items) == 9


def test_checklist_statuses_for_each_problem():
    by_key = lambda data: {i["key"]: i["status"] for i in build_checklist(data)}  # noqa: E731
    assert by_key(raw(events={"total": 0, "last_24h": 0}))["events"] == "todo"
    assert by_key(raw(events={"total": 9, "last_24h": 0}))["events"] == "warning"
    assert by_key(raw(catalog={"products": 0}))["catalog"] == "todo"
    assert by_key(raw(data_quality={"unknown_product_rate": 0.2}))["product_ids"] == "warning"
    assert by_key(raw(data_quality={"unknown_product_rate": 0.05}))["product_ids"] == "ok"
    assert by_key(raw(data_quality={"purchases_without_session_rate": 0.5}))["sessions"] == "warning"
    assert by_key(raw(data_quality={"purchase_events_30d": 0}))["purchases"] == "todo"
    assert by_key(raw(profiles={"last_computed_at": None}))["profiles"] == "todo"
    assert by_key(raw(accounts_summary={"checkout_capable": 1}))["service_account"] == "warning"
