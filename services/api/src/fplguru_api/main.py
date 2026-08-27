from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import desc, distinct, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from fplguru_core.db import dispose_engine, get_sessionmaker
from fplguru_core.models import DataSyncLog, Gameweek, Player, PlayerGwPrediction

_MODEL_VERSION = "basic-v1"


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
    except Exception as exc:
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
    known = {"fpl_bootstrap", "fpl_fixtures"}
    present = set((await db.execute(select(distinct(DataSyncLog.source)))).scalars().all())
    for source in sorted(known | present):
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


@app.get("/xp")
async def xp_list(horizon: int = Query(5, ge=1, le=5),
                  db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (await db.execute(
        select(PlayerGwPrediction, Player)
        .join(Player, Player.id == PlayerGwPrediction.player_id)
        .where(PlayerGwPrediction.model_version == _MODEL_VERSION,
               PlayerGwPrediction.horizon_gw <= horizon)
    )).all()
    agg: dict[int, dict] = {}
    for pred, player in rows:
        d = agg.setdefault(player.id, {
            "player_id": player.id, "web_name": player.web_name,
            "position": player.position, "now_cost": player.now_cost, "xp_total": 0.0,
        })
        d["xp_total"] += pred.xp
    return sorted(agg.values(), key=lambda d: d["xp_total"], reverse=True)


@app.get("/players/{player_id}/xp")
async def player_xp(player_id: int, horizon: int = Query(5, ge=1, le=5),
                    db: AsyncSession = Depends(get_db)) -> dict:
    player = (await db.execute(
        select(Player).where(Player.id == player_id)
    )).scalar_one_or_none()
    preds = (await db.execute(
        select(PlayerGwPrediction)
        .where(PlayerGwPrediction.player_id == player_id,
               PlayerGwPrediction.model_version == _MODEL_VERSION,
               PlayerGwPrediction.horizon_gw <= horizon)
        .order_by(PlayerGwPrediction.horizon_gw)
    )).scalars().all()
    if player is None or not preds:
        raise HTTPException(status_code=404, detail="no predictions for player")
    return {
        "player_id": player.id, "web_name": player.web_name, "position": player.position,
        "xp_total": float(sum(p.xp for p in preds)),
        "per_gw": [
            {"horizon_gw": p.horizon_gw, "gameweek_id": p.gameweek_id, "xp": p.xp,
             "floor": p.xp_floor, "ceiling": p.xp_ceiling}
            for p in preds
        ],
    }
