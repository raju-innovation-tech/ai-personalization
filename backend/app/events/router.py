from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.responses import success_response
from app.database.database import get_db
from app.events import service
from app.events.schemas import (
    EventAcceptedOut,
    EventBatchIn,
    EventBatchResultOut,
    EventIn,
)

router = APIRouter(prefix="/events", tags=["Event Tracking"])
logger = get_logger(__name__)


@router.post("", status_code=201)
async def create_event(payload: EventIn, db: AsyncSession = Depends(get_db)):
    key, was_duplicate = await service.ingest_single_event(db, payload)
    return success_response(
        EventAcceptedOut(
            idempotency_key=key, status="duplicate" if was_duplicate else "accepted"
        ).model_dump()
    )


@router.post("/batch", status_code=201)
async def create_events_batch(payload: EventBatchIn, db: AsyncSession = Depends(get_db)):
    # The whole batch is one atomic, race-safe bulk insert. Per-event shape
    # problems are already rejected up-front with HTTP 422 by validation, so
    # `errors` stays empty unless a future validation step adds soft failures.
    outcomes = await service.ingest_events(db, payload.events)
    await db.commit()

    results = [
        EventAcceptedOut(idempotency_key=key, status="duplicate" if dup else "accepted")
        for key, dup in outcomes
    ]
    duplicates = sum(1 for _, dup in outcomes if dup)
    accepted = len(outcomes) - duplicates

    logger.info(
        "event_batch_ingested",
        total=len(payload.events),
        accepted=accepted,
        duplicates=duplicates,
        rejected=0,
    )

    return success_response(
        EventBatchResultOut(
            accepted=accepted,
            duplicates=duplicates,
            rejected=0,
            results=results,
            errors=[],
        ).model_dump()
    )
