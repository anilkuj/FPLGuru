from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fplguru_core.settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Imperative session helper for scripts / one-off tasks.

    Does NOT commit — call ``await session.commit()`` yourself. On exit the
    session is closed (rolled back if not committed).
    """
    async with get_sessionmaker()() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose the cached engine's pool. Call from FastAPI lifespan shutdown."""
    if get_engine.cache_info().currsize:
        await get_engine().dispose()


def reset_state() -> None:
    """Clear cached settings/engine/sessionmaker.

    Used by tests and by the worker's per-task engine reset.
    Does not dispose the dropped engine's pool; acceptable for tests.
    """
    get_sessionmaker.cache_clear()
    get_engine.cache_clear()
    get_settings.cache_clear()
