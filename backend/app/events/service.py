import hashlib
import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database.models.customer import EcommerceCustomer
from app.database.models.event import UserEvent
from app.events.schemas import EventIn

logger = get_logger(__name__)


def derive_idempotency_key(event: EventIn) -> str:
    """
    Build a stable key when the client doesn't supply one, so that a
    network retry of the exact same event does not get double-counted.
    """
    raw = "|".join(
        [
            event.event_type.value,
            event.external_user_id,
            event.product_id or "",
            event.session_id or "",
            event.timestamp.isoformat(),
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


async def _upsert_customers_seen(db: AsyncSession, seen: dict[str, tuple[datetime, datetime]]) -> None:
    """
    One statement for all customers touched by a batch.

    Rows are sorted by external_user_id so concurrent batches always take
    row locks in the same order (prevents deadlocks). GREATEST/LEAST ignore
    NULLs in PostgreSQL, so first/last-seen are maintained correctly.
    """
    if not seen:
        return
    rows = [
        {
            "id": uuid.uuid4(),
            "external_user_id": user_id,
            "first_seen_at": first,
            "last_seen_at": last,
        }
        for user_id, (first, last) in sorted(seen.items())
    ]
    stmt = pg_insert(EcommerceCustomer).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[EcommerceCustomer.external_user_id],
        set_={
            "first_seen_at": func.least(EcommerceCustomer.first_seen_at, stmt.excluded.first_seen_at),
            "last_seen_at": func.greatest(EcommerceCustomer.last_seen_at, stmt.excluded.last_seen_at),
        },
    )
    await db.execute(stmt)


async def ingest_events(db: AsyncSession, events: list[EventIn]) -> list[tuple[str, bool]]:
    """
    Race-safe bulk ingestion. Does NOT commit (caller owns the transaction).

    Duplicate detection is done by PostgreSQL itself via
    INSERT .. ON CONFLICT DO NOTHING on the unique idempotency_key, so two
    concurrent requests carrying the same event can never both insert it
    and never raise IntegrityError (the old check-then-insert approach
    returned HTTP 500 under concurrent retries).

    Returns one (idempotency_key, was_duplicate) tuple per input event,
    in input order.
    """
    keyed = [(e.idempotency_key or derive_idempotency_key(e), e) for e in events]

    # First occurrence of a key inside this batch wins; later ones are duplicates.
    unique: dict[str, EventIn] = {}
    for key, event in keyed:
        unique.setdefault(key, event)

    # Sorted by key => consistent lock order across concurrent transactions.
    rows = [
        {
            "id": uuid.uuid4(),
            "external_user_id": event.external_user_id,
            "event_type": event.event_type,
            "product_id": event.product_id,
            "session_id": event.session_id,
            "platform": event.platform,
            "event_metadata": event.metadata,
            "occurred_at": event.timestamp,
            "idempotency_key": key,
        }
        for key, event in sorted(unique.items())
    ]

    result = await db.execute(
        pg_insert(UserEvent)
        .values(rows)
        .on_conflict_do_nothing(index_elements=[UserEvent.idempotency_key])
        .returning(UserEvent.idempotency_key)
    )
    inserted_keys = set(result.scalars().all())

    seen: dict[str, tuple[datetime, datetime]] = {}
    for key in inserted_keys:
        event = unique[key]
        first, last = seen.get(event.external_user_id, (event.timestamp, event.timestamp))
        seen[event.external_user_id] = (min(first, event.timestamp), max(last, event.timestamp))
    await _upsert_customers_seen(db, seen)

    outcomes: list[tuple[str, bool]] = []
    reported: set[str] = set()
    for key, _ in keyed:
        accepted = key in inserted_keys and key not in reported
        reported.add(key)
        outcomes.append((key, not accepted))
    return outcomes


async def ingest_single_event(db: AsyncSession, event: EventIn) -> tuple[str, bool]:
    (key, was_duplicate), = await ingest_events(db, [event])
    await db.commit()
    logger.info(
        "event_ingested",
        event_type=event.event_type.value,
        external_user_id=event.external_user_id,
        duplicate=was_duplicate,
    )
    return key, was_duplicate
