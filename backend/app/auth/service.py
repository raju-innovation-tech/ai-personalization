import hashlib
import json
import secrets
import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email import send_otp_email
from app.core.health import get_redis
from app.core.logging import get_logger
from app.core.responses import NotFoundError, RateLimitError, UnauthorizedError
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    create_reset_token,
    decode_token_or_raise,
    hash_password,
    verify_password,
)
from app.database.models.user import User, UserRole

logger = get_logger("app.auth.service")

# Production OTP Security Rules
_OTP_TTL_SECONDS = 300            # 5 minutes expiration
_RESEND_COOLDOWN_SECONDS = 60     # 60 seconds resend cooldown
_MAX_OTP_ATTEMPTS = 5             # Maximum 5 verification attempts

# In-memory fallback if Redis is down: email.lower() -> dict(code, expires_at, last_sent_at, attempts)
_IN_MEMORY_OTP_STORE: dict[str, dict] = {}


def _mask_email(email: str) -> str:
    """Mask email for production audit logs (e.g. ad***@example.com)."""
    try:
        user_part, domain = email.split("@", 1)
        if len(user_part) <= 2:
            masked_user = user_part[0] + "***"
        else:
            masked_user = user_part[:2] + "***" + user_part[-1]
        return f"{masked_user}@{domain}"
    except Exception:
        return "***@***"


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


async def _get_otp_record(email: str) -> dict | None:
    """Retrieve OTP record from Redis or in-memory fallback."""
    redis_key = f"auth:otp:{email}"
    try:
        redis = get_redis()
        raw = await redis.get(redis_key)
        if raw:
            return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.debug("redis_get_otp_failed", error=str(exc))

    if email in _IN_MEMORY_OTP_STORE:
        record = _IN_MEMORY_OTP_STORE[email]
        if time.time() <= record["expires_at"]:
            return record
        _IN_MEMORY_OTP_STORE.pop(email, None)

    return None


async def _save_otp_record(email: str, record: dict) -> None:
    """Save OTP record with 5-minute TTL in Redis and memory."""
    ttl = max(1, int(record["expires_at"] - time.time()))
    _IN_MEMORY_OTP_STORE[email] = record

    redis_key = f"auth:otp:{email}"
    try:
        redis = get_redis()
        await redis.setex(redis_key, ttl, json.dumps(record))
    except Exception as exc:  # noqa: BLE001
        logger.debug("redis_save_otp_failed", error=str(exc))


async def _delete_otp_record(email: str) -> None:
    """Delete OTP record upon success or maximum attempts exceeded."""
    _IN_MEMORY_OTP_STORE.pop(email, None)
    redis_key = f"auth:otp:{email}"
    try:
        redis = get_redis()
        await redis.delete(redis_key)
    except Exception:  # noqa: BLE001
        pass


async def request_password_reset(db: AsyncSession, email: str) -> dict:
    """
    Generate a secure 6-digit OTP, enforce 60s cooldown, dispatch via email delivery.
    Never exposes raw OTP in responses or console.
    """
    normalized_email = email.strip().lower()

    # 1. Check Resend Cooldown (60 seconds)
    existing_record = await _get_otp_record(normalized_email)
    now = time.time()
    if existing_record:
        elapsed = now - existing_record.get("last_sent_at", 0)
        if elapsed < _RESEND_COOLDOWN_SECONDS:
            remaining = int(_RESEND_COOLDOWN_SECONDS - elapsed)
            raise RateLimitError(
                f"Please wait {remaining} seconds before requesting a new verification code.",
                code="OTP_COOLDOWN",
            )

    # 2. Look up user
    result = await db.execute(select(User).where(User.email.ilike(normalized_email)))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        logger.info("password_reset_ignored_unknown_user", email=_mask_email(normalized_email))
        return {
            "message": "If an account exists with this email, a verification code has been sent.",
        }

    # 3. Generate secure 6-digit OTP
    code = f"{secrets.randbelow(900000) + 100000}"
    expires_at = now + _OTP_TTL_SECONDS

    record = {
        "code": code,
        "expires_at": expires_at,
        "last_sent_at": now,
        "attempts": 0,
    }
    await _save_otp_record(normalized_email, record)

    # 4. Dispatch real email via configured SMTP
    await send_otp_email(to_email=user.email, otp=code, user_name=user.full_name)

    logger.info("password_reset_otp_generated", email=_mask_email(normalized_email))

    return {
        "message": "A 6-digit verification code has been sent to your registered email address.",
    }


async def reset_password(db: AsyncSession, email: str, code: str, new_password: str) -> dict:
    """
    Verify OTP with maximum 5 attempts, update password, and create an authenticated session.
    """
    normalized_email = email.strip().lower()
    clean_code = code.strip()

    if len(new_password) < 6:
        raise UnauthorizedError("Password must be at least 6 characters.", code="WEAK_PASSWORD")

    # 1. Fetch OTP Record
    record = await _get_otp_record(normalized_email)
    now = time.time()

    if not record or now > record.get("expires_at", 0):
        await _delete_otp_record(normalized_email)
        raise UnauthorizedError("Verification code has expired. Please request a new code.", code="OTP_EXPIRED")

    # 2. Check maximum verification attempts (5 max)
    current_attempts = record.get("attempts", 0)
    if current_attempts >= _MAX_OTP_ATTEMPTS:
        await _delete_otp_record(normalized_email)
        raise UnauthorizedError(
            "Maximum verification attempts exceeded. Please request a new code.",
            code="MAX_ATTEMPTS_EXCEEDED",
        )

    # 3. Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(record.get("code", ""), clean_code):
        record["attempts"] = current_attempts + 1
        await _save_otp_record(normalized_email, record)
        remaining = _MAX_OTP_ATTEMPTS - record["attempts"]

        if remaining <= 0:
            await _delete_otp_record(normalized_email)
            raise UnauthorizedError(
                "Maximum verification attempts exceeded. Please request a new code.",
                code="MAX_ATTEMPTS_EXCEEDED",
            )

        raise UnauthorizedError(
            f"Invalid verification code. {remaining} attempt(s) remaining.",
            code="INVALID_OTP",
        )

    # 4. Look up user and update password
    result = await db.execute(select(User).where(User.email.ilike(normalized_email)).with_for_update())
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        await _delete_otp_record(normalized_email)
        raise NotFoundError("User not found or inactive.", code="USER_NOT_FOUND")

    user.hashed_password = hash_password(new_password)
    user.refresh_token_hash = None
    db.add(user)
    await db.commit()

    # 5. Invalidate the used OTP
    await _delete_otp_record(normalized_email)

    # 6. Create valid authenticated session
    access_token, refresh_token = await issue_tokens(db, user)

    logger.info("password_reset_successful", email=_mask_email(normalized_email), user_id=str(user.id))

    return {
        "message": "Password reset successfully. You are now logged in.",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
        },
    }
