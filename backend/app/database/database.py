"""
Async SQLAlchemy engine and session factory.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

connect_args = {}
if "asyncpg" in settings.DATABASE_URL:
    connect_args = {"command_timeout": 30.0, "server_settings": {"statement_timeout": "30000"}}

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=getattr(settings, "DB_POOL_TIMEOUT_SECONDS", 20.0),
    pool_recycle=getattr(settings, "DB_POOL_RECYCLE_SECONDS", 1800),
    pool_pre_ping=True,
    connect_args=connect_args,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a request-scoped DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
