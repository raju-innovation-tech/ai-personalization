import pytest
from sqlalchemy import select

from app.core.security import verify_password
from app.database.models.user import User, UserRole
from scripts.create_user import create_user

pytestmark = pytest.mark.asyncio


async def test_create_then_duplicate_then_update(db_session):
    assert await create_user(db_session, email=" Shop@Example.com ", password="long-enough-1", role=UserRole.ADMIN, full_name="Shop") == "created"
    user = (await db_session.execute(select(User).where(User.email == "shop@example.com"))).scalar_one()
    assert user.role == UserRole.ADMIN and user.full_name == "Shop" and verify_password("long-enough-1", user.hashed_password)

    with pytest.raises(ValueError, match="already exists"):
        await create_user(db_session, email="shop@example.com", password="long-enough-1", role=UserRole.ADMIN)

    assert await create_user(db_session, email="shop@example.com", password="another-pass-2", role=UserRole.MARKETING_MANAGER, update=True) == "updated"
    await db_session.refresh(user)
    assert user.role == UserRole.MARKETING_MANAGER and verify_password("another-pass-2", user.hashed_password)


async def test_validation(db_session):
    with pytest.raises(ValueError, match="valid email"):
        await create_user(db_session, email="nope", password="long-enough-1", role=UserRole.ADMIN)
    with pytest.raises(ValueError, match="at least"):
        await create_user(db_session, email="a@b.co", password="short", role=UserRole.ADMIN)
