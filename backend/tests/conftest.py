"""
Test configuration.

SAFETY: tests create and DROP every table. They must never touch the
development database, so this module ALWAYS points the app at a
separate "<db>_test" database (created automatically if missing), even
when DATABASE_URL is already set in the environment (e.g. inside the
Docker container, where env_file injects the dev DB URL).
"""
import os

import psycopg2
from sqlalchemy.engine import make_url

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")

_DEFAULT_URL = "postgresql+asyncpg://ai_personalization:ai_personalization@localhost:5433/ai_personalization"


def _as_test_url(raw: str):
    url = make_url(raw)
    if not (url.database or "").endswith("_test"):
        url = url.set(database=f"{url.database}_test")
    return url


def _detect_db_url():
    candidates = [
        os.environ.get("TEST_DATABASE_URL"),
        "postgresql+asyncpg://raju:raju-dev-708433@127.0.0.1:5433/ai_personalization",
        "postgresql+asyncpg://raju:raju-dev-708433@127.0.0.1:5432/ai_personalization",
        "postgresql+asyncpg://ai_personalization:ai_personalization@127.0.0.1:5433/ai_personalization",
        "postgresql+asyncpg://ai_personalization:ai_personalization@127.0.0.1:5432/ai_personalization",
    ]
    if os.environ.get("DATABASE_URL") and "@postgres:" not in os.environ.get("DATABASE_URL", ""):
        candidates.append(os.environ.get("DATABASE_URL"))
    for raw in candidates:
        if not raw:
            continue
        try:
            url = make_url(raw)
            conn = psycopg2.connect(
                host=url.host,
                port=url.port or 5433,
                user=url.username,
                password=url.password,
                dbname=url.database or "postgres",
                connect_timeout=1,
            )
            conn.close()
            return raw
        except Exception:
            continue
    return "postgresql+asyncpg://raju:raju-dev-708433@127.0.0.1:5433/ai_personalization"


_async_url = _as_test_url(os.environ.get("TEST_DATABASE_URL") or _detect_db_url())
_sync_url = _async_url.set(drivername="postgresql+psycopg2")

os.environ["DATABASE_URL"] = _async_url.render_as_string(hide_password=False)
os.environ["DATABASE_URL_SYNC"] = _sync_url.render_as_string(hide_password=False)
assert _async_url.database.endswith("_test"), "refusing to run tests against a non-test database"


def _ensure_test_database_exists() -> None:
    try:
        conn = psycopg2.connect(
            host=_async_url.host,
            port=_async_url.port or 5433,
            user=_async_url.username,
            password=_async_url.password,
            dbname="ai_personalization",
            connect_timeout=3,
        )
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (_async_url.database,))
                if cur.fetchone() is None:
                    cur.execute(f'CREATE DATABASE "{_async_url.database}"')
        finally:
            conn.close()
    except Exception as e:
        import warnings
        warnings.warn(f"Could not connect to PostgreSQL to create test database: {e}")


_ensure_test_database_exists()

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

settings.DATABASE_URL = _async_url.render_as_string(hide_password=False)
settings.DATABASE_URL_SYNC = _sync_url.render_as_string(hide_password=False)

from app.database.database import Base, get_db
from app.main import app

# A fresh engine per test function avoids "attached to a different loop"
# errors: pytest-asyncio (function-scoped by default) tears down and
# recreates the event loop between tests, but a module-level engine's
# connection pool is bound to whichever loop created it.


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncSession:
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function", autouse=False)
def override_get_db(db_engine):
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)

    async def _get_db_override():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture(scope="function")
async def client(override_get_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def _reset_recommendation_cache():
    """The model snapshot is cached in-process; every test starts with a fresh DB."""
    from app.recommendations.service import reset_snapshot_cache

    reset_snapshot_cache()
    yield
    reset_snapshot_cache()


async def _login_headers(client, db_session, email: str, role) -> dict:
    from app.core.security import hash_password
    from app.database.models.user import User

    db_session.add(
        User(email=email, hashed_password=hash_password("Password123!"), full_name="Tester", role=role, is_active=True)
    )
    await db_session.commit()
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


@pytest_asyncio.fixture
async def admin_headers(client, db_session):
    from app.database.models.user import UserRole

    return await _login_headers(client, db_session, "admin@test.com", UserRole.ADMIN)


@pytest_asyncio.fixture
async def viewer_headers(client, db_session):
    from app.database.models.user import UserRole

    return await _login_headers(client, db_session, "viewer@test.com", UserRole.VIEWER)


@pytest_asyncio.fixture
async def marketing_headers(client, db_session):
    from app.database.models.user import UserRole

    return await _login_headers(client, db_session, "marketing@test.com", UserRole.MARKETING_MANAGER)


@pytest_asyncio.fixture
async def super_headers(client, db_session):
    from app.database.models.user import UserRole

    return await _login_headers(client, db_session, "super@test.com", UserRole.SUPER_ADMIN)
