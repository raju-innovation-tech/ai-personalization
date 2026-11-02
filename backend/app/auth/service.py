import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.responses import UnauthorizedError
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token_or_raise,
    verify_password,
)
from app.database.models.user import User, UserRole


def _hash_refresh_token(token: str) -> str:
    # Refresh tokens are stored hashed so a DB leak doesn't expose usable tokens.
    return hashlib.sha256(token.encode()).hexdigest()


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        raise UnauthorizedError("Invalid email or password", code="INVALID_CREDENTIALS")

    return user


async def issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    access_token = create_access_token(subject=str(user.id), role=user.role.value)
    refresh_token = create_refresh_token(subject=str(user.id))

    user.refresh_token_hash = _hash_refresh_token(refresh_token)
    db.add(user)
    await db.commit()

    return access_token, refresh_token


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> tuple[str, str]:
    try:
        payload = decode_token_or_raise(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise UnauthorizedError(str(exc), code="INVALID_REFRESH_TOKEN") from exc

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except ValueError as exc:
        raise UnauthorizedError("Invalid refresh token subject", code="INVALID_REFRESH_TOKEN") from exc

    # FOR UPDATE: concurrent refreshes with the same token are serialized, so a
    # rotated-away refresh token can never be accepted twice.
    result = await db.execute(select(User).where(User.id == user_id).with_for_update())
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive", code="INVALID_REFRESH_TOKEN")

    if user.refresh_token_hash != _hash_refresh_token(refresh_token):
        # Token reuse or a stale/revoked token — force re-login.
        raise UnauthorizedError("Refresh token has been revoked", code="REFRESH_TOKEN_REVOKED")

    # Rotate: issue a brand-new pair, invalidate the old refresh token.
    return await issue_tokens(db, user)


async def logout_user(db: AsyncSession, user: User) -> None:
    user.refresh_token_hash = None
    db.add(user)
    await db.commit()


async def get_first_super_admin_or_none(db: AsyncSession) -> User | None:
    result = await db.execute(select(User).where(User.role == UserRole.SUPER_ADMIN))
    return result.scalars().first()
