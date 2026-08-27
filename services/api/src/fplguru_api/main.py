from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fplguru_entrysync import sync_entry
from fplguru_fdr import compute_fdr
from sqlalchemy import desc, distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from fplguru_core.db import dispose_engine, get_sessionmaker
from fplguru_core.models import (
    DataSyncLog,
    EntryGwHistory,
    EntryPick,
    Fixture,
    Gameweek,
    LinkedTeam,
    Player,
    PlayerGwPrediction,
    Team,
)

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


@app.get("/fdr")
async def fdr(
    horizon: int = Query(5, ge=1, le=10),
    start_gw: int | None = Query(None, ge=1, le=38),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if start_gw is None:
        nxt = (await db.execute(
            select(Gameweek).where(Gameweek.is_current)
        )).scalar_one_or_none()
        if nxt is None:
            nxt = (await db.execute(
                select(Gameweek).where(Gameweek.is_next)
            )).scalar_one_or_none()
        start_gw = nxt.id if nxt else 1
    teams = [
        {"id": t.id, "short_name": t.short_name,
         "strength_overall_home": t.strength_overall_home,
         "strength_overall_away": t.strength_overall_away}
        for t in (await db.execute(select(Team))).scalars().all()
    ]
    gws = [
        {"id": g.id, "is_next": g.is_next, "finished": g.finished}
        for g in (await db.execute(select(Gameweek))).scalars().all()
    ]
    fixtures = [
        {"id": f.id, "gameweek_id": f.gameweek_id, "home_team_id": f.home_team_id,
         "away_team_id": f.away_team_id, "home_score": f.home_score,
         "away_score": f.away_score, "finished": f.finished}
        for f in (await db.execute(select(Fixture))).scalars().all()
    ]
    return {
        "start_gw": start_gw,
        "horizon": horizon,
        "teams": compute_fdr(teams, fixtures, gws, start_gw=start_gw, horizon=horizon),
    }


@app.post("/link/{entry_id}")
async def link_entry(entry_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await sync_entry(entry_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"could not sync entry {entry_id}") from exc
    lt = (await db.execute(
        select(LinkedTeam).where(LinkedTeam.fpl_entry_id == entry_id)
    )).scalar_one()
    return {"fpl_entry_id": lt.fpl_entry_id, "manager_name": lt.manager_name,
            "linked_team_id": lt.id}


async def _linked_or_404(db: AsyncSession, entry_id: int) -> LinkedTeam:
    lt = (await db.execute(
        select(LinkedTeam).where(LinkedTeam.fpl_entry_id == entry_id)
    )).scalar_one_or_none()
    if lt is None:
        raise HTTPException(status_code=404, detail="entry not linked")
    return lt


@app.get("/entries/{entry_id}")
async def get_entry(entry_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    lt = await _linked_or_404(db, entry_id)
    latest_pick_gw = (await db.execute(
        select(func.max(EntryPick.gameweek_id)).where(EntryPick.linked_team_id == lt.id)
    )).scalar()
    rows = (await db.execute(
        select(EntryPick, Player).join(Player, Player.id == EntryPick.player_id)
        .where(EntryPick.linked_team_id == lt.id, EntryPick.gameweek_id == latest_pick_gw)
        .order_by(EntryPick.slot)
    )).all()
    xp_by_player: dict[int, float] = {}
    if rows:
        pids = [pl.id for _, pl in rows]
        for pid, total in (await db.execute(
            select(PlayerGwPrediction.player_id, func.sum(PlayerGwPrediction.xp))
            .where(PlayerGwPrediction.player_id.in_(pids),
                   PlayerGwPrediction.model_version == _MODEL_VERSION)
            .group_by(PlayerGwPrediction.player_id)
        )).all():
            xp_by_player[pid] = float(total)
    return {
        "fpl_entry_id": lt.fpl_entry_id,
        "manager_name": lt.manager_name,
        "last_synced_at": lt.last_synced_at.isoformat() if lt.last_synced_at else None,
        "picks_gameweek_id": latest_pick_gw,
        "picks": [
            {"slot": ep.slot, "player_id": pl.id, "web_name": pl.web_name,
             "position": pl.position, "now_cost": pl.now_cost, "multiplier": ep.multiplier,
             "is_captain": ep.is_captain, "is_vice": ep.is_vice,
             "xp": xp_by_player.get(pl.id, 0.0)}
            for ep, pl in rows
        ],
    }


@app.get("/entries/{entry_id}/history")
async def get_entry_history(entry_id: int, db: AsyncSession = Depends(get_db)) -> list[dict]:
    lt = await _linked_or_404(db, entry_id)
    rows = (await db.execute(
        select(EntryGwHistory).where(EntryGwHistory.linked_team_id == lt.id)
        .order_by(EntryGwHistory.gameweek_id)
    )).scalars().all()
    return [
        {"gameweek_id": h.gameweek_id, "points": h.points, "total_points": h.total_points,
         "overall_rank": h.overall_rank, "bank": h.bank, "team_value": h.team_value,
         "transfers": h.transfers, "transfer_cost": h.transfer_cost,
         "points_on_bench": h.points_on_bench}
        for h in rows
    ]


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
