import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.auth import service
from app.core.responses import RateLimitError, UnauthorizedError


def test_otp_generation_and_masking():
    email = "admin@example.com"
    masked = service._mask_email(email)
    assert masked == "ad***n@example.com"
    assert "admin@" not in masked


def test_otp_cooldown_and_expiration():
    async def _test():
        service._IN_MEMORY_OTP_STORE.clear()

        # Mock DB user
        db = AsyncMock()
        mock_user = AsyncMock()
        mock_user.email = "test@example.com"
        mock_user.full_name = "Test User"
        mock_user.is_active = True
        mock_res = AsyncMock()
        mock_res.scalar_one_or_none.return_value = mock_user
        db.execute.return_value = mock_res

        with patch("app.auth.service.send_otp_email", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            # 1. First request -> Success
            res1 = await service.request_password_reset(db, "test@example.com")
            assert "verification code" in res1["message"].lower()
            assert "reset_code" not in res1
            mock_send.assert_awaited_once()

            # 2. Immediate second request within 60s -> RateLimitError (OTP_COOLDOWN)
            with pytest.raises(RateLimitError) as exc_info:
                await service.request_password_reset(db, "test@example.com")
            assert exc_info.value.code == "OTP_COOLDOWN"

            # 3. Simulate OTP expiration after 301 seconds
            record = service._IN_MEMORY_OTP_STORE["test@example.com"]
            record["expires_at"] = time.time() - 1

            with pytest.raises(UnauthorizedError) as exc_expired:
                await service.reset_password(db, "test@example.com", record["code"], "NewPass123!")
            assert exc_expired.value.code == "OTP_EXPIRED"

    asyncio.run(_test())


def test_otp_max_5_attempts():
    async def _test():
        service._IN_MEMORY_OTP_STORE.clear()

        # Setup valid OTP
        service._IN_MEMORY_OTP_STORE["attempt@example.com"] = {
            "code": "888999",
            "expires_at": time.time() + 300,
            "last_sent_at": time.time(),
            "attempts": 0,
        }

        db = AsyncMock()

        # Attempts 1 to 4 should increment and show remaining attempts
        for attempt in range(1, 5):
            with pytest.raises(UnauthorizedError) as exc_info:
                await service.reset_password(db, "attempt@example.com", "000000", "NewPass123!")
            assert exc_info.value.code == "INVALID_OTP"
            assert f"{5 - attempt} attempt(s) remaining" in exc_info.value.message

        # 5th failed attempt should lock out with MAX_ATTEMPTS_EXCEEDED
        with pytest.raises(UnauthorizedError) as exc_max:
            await service.reset_password(db, "attempt@example.com", "000000", "NewPass123!")
        assert exc_max.value.code == "MAX_ATTEMPTS_EXCEEDED"

        # Record should be deleted after exceeding maximum attempts
        assert "attempt@example.com" not in service._IN_MEMORY_OTP_STORE

    asyncio.run(_test())

