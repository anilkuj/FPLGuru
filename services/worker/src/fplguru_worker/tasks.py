import asyncio
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from fplguru_core.db import get_sessionmaker
from fplguru_core.models import DataSyncLog, Fixture, Gameweek, Player, Team
from fplguru_core.settings import get_settings
from fplguru_fpl_client import FplClient
from fplguru_ingest.fpl import (
    normalize_fixtures,
    normalize_gameweeks,
    normalize_players,
    normalize_teams,
)
from fplguru_worker.app import celery_app


async def _upsert(session, model, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(model).values(rows)
    update_cols = {
        c.name: stmt.excluded[c.name]
        for c in model.__table__.columns
        if c.name not in ("id",)
    }
    if "updated_at" in model.__table__.columns:
        update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols)
    await session.execute(stmt)


async def _record(session, source: str, status: str, started: datetime, detail: str = "") -> None:
    session.add(
        DataSyncLog(
            source=source, status=status, detail=detail,
            started_at=started, finished_at=datetime.now(UTC),
        )
    )


async def _sync_bootstrap() -> None:
    started = datetime.now(UTC)
    client = FplClient(get_settings().fpl_api_base)
    try:
        data = await client.bootstrap_static()
    finally:
        await client.aclose()
    maker = get_sessionmaker()
    async with maker() as session:
        try:
            async with session.begin():
                await _upsert(session, Team, normalize_teams(data))
                await _upsert(session, Gameweek, normalize_gameweeks(data))
                await _upsert(session, Player, normalize_players(data))
                await _record(session, "fpl_bootstrap", "ok", started)
        except Exception as exc:  # noqa: BLE001
            async with session.begin():
                await _record(session, "fpl_bootstrap", "error", started, str(exc)[:500])
            raise


async def _sync_fixtures() -> None:
    started = datetime.now(UTC)
    client = FplClient(get_settings().fpl_api_base)
    try:
        data = await client.fixtures()
    finally:
        await client.aclose()
    maker = get_sessionmaker()
    async with maker() as session:
        try:
            async with session.begin():
                await _upsert(session, Fixture, normalize_fixtures(data))
                await _record(session, "fpl_fixtures", "ok", started)
        except Exception as exc:  # noqa: BLE001
            async with session.begin():
                await _record(session, "fpl_fixtures", "error", started, str(exc)[:500])
            raise


@celery_app.task(name="sync_bootstrap", bind=True, max_retries=3, default_retry_delay=60)
def sync_bootstrap(self) -> None:
    try:
        asyncio.run(_sync_bootstrap())
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc)


@celery_app.task(name="sync_fixtures", bind=True, max_retries=3, default_retry_delay=60)
def sync_fixtures(self) -> None:
    try:
        asyncio.run(_sync_fixtures())
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc)
