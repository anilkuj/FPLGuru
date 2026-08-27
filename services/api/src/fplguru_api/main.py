from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from fplguru_core.db import dispose_engine, get_sessionmaker
from fplguru_core.models import DataSyncLog, Gameweek


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


app = FastAPI(title="FPLGuru API", version="0.1.0", lifespan=lifespan)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Read-only request session. Does NOT commit — a mutating route must
    manage its own transaction (see fplguru_core.db.session_scope)."""
    async with get_sessionmaker()() as session:
        yield session


def _gw(row: Gameweek) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "deadline_time": row.deadline_time.isoformat(),
        "is_current": row.is_current,
        "is_next": row.is_next,
        "finished": row.finished,
        "average_entry_score": row.average_entry_score,
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ready"}


@app.get("/gameweeks")
async def list_gameweeks(db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (await db.execute(select(Gameweek).order_by(Gameweek.id))).scalars().all()
    return [_gw(r) for r in rows]


@app.get("/gameweeks/current")
async def current_gameweek(db: AsyncSession = Depends(get_db)) -> dict | None:
    row = (
        await db.execute(select(Gameweek).where(Gameweek.is_current))
    ).scalar_one_or_none()
    if row is None:
        row = (
            await db.execute(select(Gameweek).where(Gameweek.is_next))
        ).scalar_one_or_none()
    return _gw(row) if row else None


@app.get("/status")
async def status(db: AsyncSession = Depends(get_db)) -> dict:
    sources: dict[str, dict] = {}
    for source in ("fpl_bootstrap", "fpl_fixtures"):
        row = (
            await db.execute(
                select(DataSyncLog)
                .where(DataSyncLog.source == source, DataSyncLog.status == "ok")
                .order_by(desc(DataSyncLog.finished_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        sources[source] = (
            {"status": "ok", "as_of": row.finished_at.isoformat()}
            if row
            else {"status": "unknown", "as_of": None}
        )
    return {"sources": sources}
