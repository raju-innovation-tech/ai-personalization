import pytest

pytestmark = pytest.mark.asyncio


async def test_create_event_success(client):
    payload = {
        "event_type": "PRODUCT_VIEW",
        "external_user_id": "USER_10025",
        "product_id": "PROD_500",
        "session_id": "SESSION_123",
        "platform": "mobile",
        "timestamp": "2026-09-25T10:30:00Z",
        "metadata": {"category": "electronics"},
    }

    response = await client.post("/api/v1/events", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "accepted"


async def test_duplicate_event_is_idempotent(client):
    payload = {
        "event_type": "PRODUCT_VIEW",
        "external_user_id": "USER_10025",
        "product_id": "PROD_500",
        "session_id": "SESSION_123",
        "platform": "mobile",
        "timestamp": "2026-09-25T10:30:00Z",
        "idempotency_key": "fixed-key-123",
    }

    first = await client.post("/api/v1/events", json=payload)
    second = await client.post("/api/v1/events", json=payload)

    assert first.json()["data"]["status"] == "accepted"
    assert second.json()["data"]["status"] == "duplicate"


async def test_event_requires_timezone_aware_timestamp(client):
    payload = {
        "event_type": "PRODUCT_VIEW",
        "external_user_id": "USER_10025",
        "timestamp": "2026-09-25T10:30:00",  # no timezone
    }

    response = await client.post("/api/v1/events", json=payload)
    assert response.status_code == 422


async def test_batch_events(client):
    payload = {
        "events": [
            {
                "event_type": "PRODUCT_VIEW",
                "external_user_id": "USER_10025",
                "product_id": "PROD_500",
                "timestamp": "2026-09-25T10:30:00Z",
            },
            {
                "event_type": "ADD_TO_CART",
                "external_user_id": "USER_10025",
                "product_id": "PROD_500",
                "timestamp": "2026-09-25T10:31:00Z",
            },
        ]
    }

    response = await client.post("/api/v1/events/batch", json=payload)

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["accepted"] == 2
    assert body["rejected"] == 0


# ---------------------------------------------------------------------------
# Regression tests for bugs found during the functional audit
# ---------------------------------------------------------------------------
import asyncio
import uuid


def _event(**overrides):
    base = {
        "event_type": "PRODUCT_VIEW",
        "external_user_id": "USER_RACE",
        "product_id": "PROD_1",
        "timestamp": "2026-09-25T10:30:00Z",
    }
    base.update(overrides)
    return base


async def test_concurrent_duplicate_events_never_500(client):
    key = str(uuid.uuid4())
    responses = await asyncio.gather(
        *[client.post("/api/v1/events", json=_event(idempotency_key=key)) for _ in range(8)]
    )
    assert all(r.status_code == 201 for r in responses)
    statuses = sorted(r.json()["data"]["status"] for r in responses)
    assert statuses.count("accepted") == 1
    assert statuses.count("duplicate") == 7


async def test_concurrent_overlapping_batches_never_500(client):
    key = str(uuid.uuid4())

    def payload():
        return {
            "events": [
                _event(idempotency_key=key),
                _event(external_user_id=f"U_{uuid.uuid4().hex[:8]}", timestamp="2026-09-25T11:00:00Z"),
            ]
        }

    responses = await asyncio.gather(*[client.post("/api/v1/events/batch", json=payload()) for _ in range(6)])
    assert all(r.status_code == 201 for r in responses)
    assert sum(r.json()["data"]["accepted"] for r in responses) == 1 + 6  # shared key once + 6 unique


async def test_duplicate_inside_one_batch_is_reported(client):
    key = str(uuid.uuid4())
    response = await client.post(
        "/api/v1/events/batch",
        json={"events": [_event(idempotency_key=key), _event(idempotency_key=key)]},
    )
    body = response.json()["data"]
    assert (body["accepted"], body["duplicates"]) == (1, 1)
    assert [r["status"] for r in body["results"]] == ["accepted", "duplicate"]


async def test_nul_character_in_metadata_is_422_not_500(client):
    response = await client.post("/api/v1/events", json=_event(metadata={"note": "bad\u0000value"}))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_customer_first_and_last_seen_tracked(client, db_session):
    from sqlalchemy import select

    from app.database.models.customer import EcommerceCustomer

    for ts in ("2026-09-25T10:00:00Z", "2026-09-27T10:00:00Z", "2026-09-26T10:00:00Z"):
        r = await client.post("/api/v1/events", json=_event(external_user_id="USER_SEEN", timestamp=ts))
        assert r.status_code == 201

    row = (
        await db_session.execute(select(EcommerceCustomer).where(EcommerceCustomer.external_user_id == "USER_SEEN"))
    ).scalar_one()
    assert row.first_seen_at.isoformat().startswith("2026-09-25")
    assert row.last_seen_at.isoformat().startswith("2026-09-27")
