import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from fplguru_core.db import dispose_engine, get_sessionmaker, reset_state
from fplguru_core.models import (
    DataSyncLog,
    Fixture,
    Gameweek,
    Player,
    PlayerGwStat,
    Team,
)
from fplguru_core.settings import get_settings
from fplguru_fpl_client import FplClient
from fplguru_ingest.fpl import (
    normalize_event_live,
    normalize_fixtures,
    normalize_gameweeks,
    normalize_players,
    normalize_teams,
)
from fplguru_worker.app import celery_app
from fplguru_worker.xp import compute_and_store_xp

logger = logging.getLogger("fplguru.worker")


async def _upsert(session, model, rows: list[dict]) -> int:
    if not rows:
        return 0
    present = set(rows[0])
    stmt = pg_insert(model).values(rows)
    update_cols = {
        c.name: stmt.excluded[c.name]
        for c in model.__table__.columns
        if c.name != "id" and c.name in present
    }
    if "updated_at" in model.__table__.columns:
        update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols)
    await session.execute(stmt)
    return len(rows)


async def _record(
    session, source: str, status: str, started: datetime, detail: str = ""
) -> None:
    session.add(
        DataSyncLog(
            source=source,
            status=status,
            detail=detail,
            started_at=started,
            finished_at=datetime.now(UTC),
        )
    )


async def _log_error(source: str, started: datetime, exc: Exception) -> None:
    """Record an error row on a FRESH session so a broken connection on the
    working session cannot also swallow the audit trail."""
    logger.exception("%s sync failed", source)
    try:
        async with get_sessionmaker()() as session, session.begin():
            await _record(session, source, "error", started, str(exc)[:500])
    except Exception:
        logger.exception("could not record %s error row", source)


async def _sync_bootstrap() -> None:
    started = datetime.now(UTC)
    try:
        client = FplClient(get_settings().fpl_api_base)
        try:
            data = await client.bootstrap_static()
        finally:
            await client.aclose()
        async with get_sessionmaker()() as session, session.begin():
            n_t = await _upsert(session, Team, normalize_teams(data))
            n_g = await _upsert(session, Gameweek, normalize_gameweeks(data))
            n_p = await _upsert(session, Player, normalize_players(data))
            await _record(session, "fpl_bootstrap", "ok", started)
        logger.info("bootstrap synced: %d teams / %d gameweeks / %d players", n_t, n_g, n_p)
    except Exception as exc:
        await _log_error("fpl_bootstrap", started, exc)
        raise


async def _sync_fixtures() -> None:
    started = datetime.now(UTC)
    try:
        client = FplClient(get_settings().fpl_api_base)
        try:
            data = await client.fixtures()
        finally:
            await client.aclose()
        async with get_sessionmaker()() as session, session.begin():
            if not await session.scalar(select(func.count()).select_from(Team)):
                await _record(
                    session, "fpl_fixtures", "ok", started,
                    "skipped: teams not populated yet",
                )
                logger.info("fixtures sync skipped: teams table empty")
                return
            n = await _upsert(session, Fixture, normalize_fixtures(data))
            await _record(session, "fpl_fixtures", "ok", started)
        logger.info("fixtures synced: %d rows", n)
    except Exception as exc:
        await _log_error("fpl_fixtures", started, exc)
        raise


async def sync_all() -> None:
    """Bootstrap then fixtures in one event loop — the entry point for
    manual DB population:

        python - <<'PY'
        import asyncio
        from fplguru_worker.tasks import sync_all
        asyncio.run(sync_all())
        PY
    """
    await _sync_bootstrap()
    await _sync_fixtures()


async def _run_and_dispose(coro_fn) -> None:
    """Run one sync, then drop the process-cached engine so the next Celery
    task (a fresh event loop via asyncio.run) doesn't reuse asyncpg
    connections bound to a closed loop."""
    try:
        await coro_fn()
    finally:
        await dispose_engine()
        reset_state()


@celery_app.task(name="sync_bootstrap", bind=True, max_retries=3, default_retry_delay=60)
def sync_bootstrap(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_sync_bootstrap))
    except Exception as exc:
        raise self.retry(exc=exc) from exc


@celery_app.task(name="sync_fixtures", bind=True, max_retries=3, default_retry_delay=60)
def sync_fixtures(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_sync_fixtures))
    except Exception as exc:
        raise self.retry(exc=exc) from exc


async def _upsert_stats(session, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(PlayerGwStat).values(rows)
    update_cols = {
        c: stmt.excluded[c] for c in rows[0] if c not in ("player_id", "gameweek_id")
    }
    update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(
        index_elements=["player_id", "gameweek_id"], set_=update_cols
    )
    await session.execute(stmt)


async def _sync_gw_stats() -> None:
    started = datetime.now(UTC)
    try:
        async with get_sessionmaker()() as session, session.begin():
            finished_gw_ids = (
                await session.execute(
                    select(Gameweek.id).where(Gameweek.finished.is_(True)).order_by(Gameweek.id)
                )
            ).scalars().all()
            players = {
                p.id: p for p in (await session.execute(select(Player))).scalars().all()
            }
            fixtures = (
                await session.execute(
                    select(Fixture).where(Fixture.gameweek_id.in_(finished_gw_ids))
                )
            ).scalars().all()
            side: dict[tuple[int, int], tuple[bool, int]] = {}
            for f in fixtures:
                side[(f.gameweek_id, f.home_team_id)] = (True, f.away_team_id)
                side[(f.gameweek_id, f.away_team_id)] = (False, f.home_team_id)

        if not finished_gw_ids:
            async with get_sessionmaker()() as session, session.begin():
                await _record(session, "fpl_gw_stats", "ok", started, "no finished gameweeks")
            return

        client = FplClient(get_settings().fpl_api_base)
        rows: list[dict] = []
        try:
            for gw_id in finished_gw_ids:
                payload = await client.event_live(gw_id)
                for r in normalize_event_live(gw_id, payload):
                    p = players.get(r["player_id"])
                    if p is None:
                        continue
                    was_home, opp = side.get((gw_id, p.team_id), (False, None))
                    r["was_home"] = was_home
                    r["opponent_team_id"] = opp
                    r["value"] = p.now_cost
                    rows.append(r)
        finally:
            await client.aclose()

        async with get_sessionmaker()() as session, session.begin():
            await _upsert_stats(session, rows)
            await _record(session, "fpl_gw_stats", "ok", started, f"{len(rows)} rows")
        logger.info("gw stats synced: %d rows over %d gameweeks", len(rows), len(finished_gw_ids))
    except Exception as exc:
        await _log_error("fpl_gw_stats", started, exc)
        raise


@celery_app.task(name="sync_gw_stats", bind=True, max_retries=3, default_retry_delay=60)
def sync_gw_stats(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_sync_gw_stats))
    except Exception as exc:
        raise self.retry(exc=exc) from exc


@celery_app.task(name="compute_xp", bind=True, max_retries=3, default_retry_delay=120)
def compute_xp(self) -> None:
    try:
        asyncio.run(_run_and_dispose(lambda: compute_and_store_xp(horizon=5)))
    except Exception as exc:
        raise self.retry(exc=exc) from exc
