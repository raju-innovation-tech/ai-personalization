import uuid

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.responses import ForbiddenError, UnauthorizedError
from app.core.security import TokenError, decode_token_or_raise
from app.database.database import get_db
from app.database.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if token is None:
        raise UnauthorizedError("Missing bearer token")

    try:
        payload = decode_token_or_raise(token, expected_type="access")
    except TokenError as exc:
        raise UnauthorizedError(str(exc), code="INVALID_ACCESS_TOKEN") from exc

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except ValueError as exc:
        raise UnauthorizedError("Invalid access token subject", code="INVALID_ACCESS_TOKEN") from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    return user


def require_roles(*allowed_roles: UserRole):
    """Dependency factory for RBAC: require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)"""

    async def _checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise ForbiddenError(
                f"Role '{current_user.role.value}' is not permitted to perform this action"
            )
        return current_user

    return _checker
