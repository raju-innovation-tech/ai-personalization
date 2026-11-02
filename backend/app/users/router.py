import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_roles
from app.core.logging import get_logger
from app.core.responses import NotFoundError, success_response
from app.database.database import get_db
from app.database.models.user import User, UserRole
from app.users import service
from app.users.schemas import UserCreateIn, UserUpdateIn

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])

_admin = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.get("", summary="List staff users (admin)")
async def list_users(db: AsyncSession = Depends(get_db), _actor: User = Depends(_admin)):
    users = await service.list_users(db)
    return success_response({"items": [service.user_out(u) for u in users], "total": len(users)})


@router.post("", status_code=201, summary="Create a staff user (admin)")
async def create_user(payload: UserCreateIn, db: AsyncSession = Depends(get_db), actor: User = Depends(_admin)):
    user = await service.create_user_checked(
        db, actor, email=payload.email, password=payload.password, full_name=payload.full_name, role=payload.role
    )
    logger.info("user_created", email=user.email, role=user.role.value, by=actor.email)
    return success_response(service.user_out(user))


@router.patch("/{user_id}", summary="Change name, role, active flag or password (admin)")
async def update_user(
    user_id: uuid.UUID, payload: UserUpdateIn, db: AsyncSession = Depends(get_db), actor: User = Depends(_admin)
):
    user = await service.get_user(db, user_id)
    if user is None:
        raise NotFoundError(f"User '{user_id}' not found", code="USER_NOT_FOUND")
    user = await service.update_user_checked(
        db, actor, user, full_name=payload.full_name, role=payload.role, is_active=payload.is_active, password=payload.password
    )
    logger.info("user_updated", email=user.email, by=actor.email)
    return success_response(service.user_out(user))
