from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.responses import success_response
from app.database.database import get_db
from app.database.models.user import User, UserRole
from app.integrations import service

router = APIRouter(prefix="/integrations", tags=["Integrations"])


@router.get("/status", summary="Is the shop connected and sending good data?")
async def status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    include_accounts = user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)  # emails are only for admins
    return success_response(await service.collect(db, include_accounts=include_accounts))
