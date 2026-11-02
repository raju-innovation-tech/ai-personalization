"""Keeps customer profiles fresh without any external scheduler."""
import asyncio

from app.core.config import settings
from app.core.logging import get_logger
from app.customers.service import recompute_profiles
from app.database.database import AsyncSessionLocal

logger = get_logger(__name__)

STARTUP_DELAY_SECONDS = 20


async def profile_refresh_loop() -> None:
    """Recompute every CUSTOMER_PROFILE_REFRESH_MINUTES. Safe with several workers (advisory lock)."""
    interval = settings.CUSTOMER_PROFILE_REFRESH_MINUTES * 60
    await asyncio.sleep(STARTUP_DELAY_SECONDS)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await recompute_profiles(db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - never let the loop die
            logger.error("customer_profile_refresh_failed", error=str(exc))
        await asyncio.sleep(interval)
