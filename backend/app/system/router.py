from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_roles
from app.core.responses import success_response
from app.database.database import get_db
from app.database.models.user import User, UserRole
from app.system import service

router = APIRouter(prefix="/system", tags=["System"])


@router.get("/status", summary="Versions, database, Redis, jobs and settings (admin)")
async def status(
    db: AsyncSession = Depends(get_db), _user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN))
):
    return success_response(await service.collect_status(db))


@router.get("/alerts", summary="Things that need attention (for the notification bell)")
async def alerts(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    items = await service.compute_alerts(db)
    return success_response(
        {
            "count": len(items),
            "needs_attention": sum(1 for a in items if a["severity"] in ("critical", "warning")),
            "items": items,
        }
    )
