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


@pytest_asyncio.fixture(scope="session")
async def _engine():
    # create the test database if it doesn't exist yet
    admin_url = TEST_DB_URL.rsplit("/", 1)[0] + "/postgres"
    dbname = TEST_DB_URL.rsplit("/", 1)[1]
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        exists = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": dbname}
        )
        if exists.first() is None:
            await conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    await admin.dispose()

    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
def _point_app_at_test_db(monkeypatch):
    monkeypatch.setenv("FPLGURU_DATABASE_URL", TEST_DB_URL)
    _db.reset_state()
    yield
    _db.reset_state()


@pytest_asyncio.fixture
async def db_session(_engine):
    maker = async_sessionmaker(_engine, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(_engine):
    yield
    async with _engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(
                text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE')
            )
