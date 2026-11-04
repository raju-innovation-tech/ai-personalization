from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.dependencies import get_current_user
from app.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.core.rate_limit import RateLimiter
from app.core.responses import success_response
from app.database.database import get_db
from app.database.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = get_logger(__name__)

login_rate_limiter = RateLimiter("login", limit=settings.RATE_LIMIT_LOGIN_PER_MINUTE, window_seconds=60)
forgot_rate_limiter = RateLimiter("forgot_pwd", limit=10, window_seconds=60)


@router.post("/login", dependencies=[Depends(login_rate_limiter)])
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await service.authenticate_user(db, payload.email, payload.password)
    access_token, refresh_token = await service.issue_tokens(db, user)

    logger.info("user_login", user_id=str(user.id), role=user.role.value)

    return success_response(
        TokenResponse(access_token=access_token, refresh_token=refresh_token).model_dump()
    )


@router.post("/refresh")
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    access_token, refresh_token = await service.refresh_access_token(db, payload.refresh_token)
    return success_response(
        TokenResponse(access_token=access_token, refresh_token=refresh_token).model_dump()
    )


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await service.logout_user(db, current_user)
    logger.info("user_logout", user_id=str(current_user.id))
    return success_response({"message": "Logged out successfully"})


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return success_response(UserOut.model_validate(current_user).model_dump())


@router.post("/forgot-password", dependencies=[Depends(forgot_rate_limiter)])
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await service.request_password_reset(db, payload.email)
    return success_response(result)


@router.post("/reset-password", dependencies=[Depends(forgot_rate_limiter)])
async def reset_password_endpoint(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await service.reset_password(db, payload.email, payload.code, payload.new_password)
    return success_response(result)
