import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fplguru_core import db as _db
from fplguru_core.models import Base

TEST_DB_URL = os.environ.get(
    "FPLGURU_TEST_DATABASE_URL",
    "postgresql+asyncpg://fplguru:fplguru@localhost:5432/fplguru_test",
)

_TRUNCATE_ALL = "TRUNCATE TABLE {} RESTART IDENTITY CASCADE".format(
    ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
)


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Session engine bound to a dedicated `fplguru_test` DB.

    Opt-in: only tests that request `db_session`/`db_engine` trigger it, so
    pure-unit tests don't require Postgres.
    """
    admin_url = TEST_DB_URL.rsplit("/", 1)[0] + "/postgres"
    dbname = TEST_DB_URL.rsplit("/", 1)[1]
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            exists = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": dbname}
            )
            if exists.first() is None:
                await conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    except OSError as exc:  # asyncpg ConnectionRefusedError, etc.
        raise RuntimeError(
            f"Postgres not reachable at {admin_url} — start it with "
            "`docker compose -f infra/docker-compose.yml up -d`"
        ) from exc
    finally:
        await admin.dispose()

    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def _point_app_at_test_db(monkeypatch):
    monkeypatch.setenv("FPLGURU_DATABASE_URL", TEST_DB_URL)
    _db.reset_state()
    yield
    _db.reset_state()


@pytest_asyncio.fixture
async def db_session(db_engine):
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    # teardown: release any pool the app code under test created, then wipe rows
    await _db.dispose_engine()
    async with db_engine.begin() as conn:
        await conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        await conn.execute(text(_TRUNCATE_ALL))
