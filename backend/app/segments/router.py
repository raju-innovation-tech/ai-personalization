from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.responses import NotFoundError, success_response
from app.customers import service
from app.database.database import get_db
from app.database.models.user import User
from app.segments.definitions import SEGMENT_BY_KEY

router = APIRouter(prefix="/segments", tags=["Segments"])


@router.get("", summary="All segments with sizes, revenue and the RFM grid")
async def list_segments(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return success_response(await service.segment_overview(db))


@router.get("/{key}", summary="One segment: definition and statistics")
async def get_segment(key: str, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    if key not in SEGMENT_BY_KEY:
        raise NotFoundError(f"Segment '{key}' does not exist", code="SEGMENT_NOT_FOUND")
    overview = await service.segment_overview(db)
    segment = next(s for s in overview["segments"] if s["key"] == key)
    return success_response({**segment, "profiles_computed_at": overview["profiles_computed_at"]})
