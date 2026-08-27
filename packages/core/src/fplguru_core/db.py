from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fplguru_core.settings import get_settings


@lru_cache
def get_engine():
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def session_scope() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


def reset_state() -> None:
    """Clear cached settings/engine/sessionmaker. For tests only."""
    get_sessionmaker.cache_clear()
    get_engine.cache_clear()
    get_settings.cache_clear()
