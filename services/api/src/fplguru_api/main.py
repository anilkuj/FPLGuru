import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fplguru_entrysync import sync_entry
from fplguru_fdr import compute_fdr
from pydantic import BaseModel
from sqlalchemy import desc, distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from fplguru_api.llm import generate_within_budget
from fplguru_captain import rank_captains, rationale_prompt
from fplguru_core.db import dispose_engine, get_sessionmaker
from fplguru_core.models import (
    DEFAULT_REMINDER_OFFSETS,
    Alert,
    CaptainRationale,
    DataSyncLog,
    EntryGwHistory,
    EntryPick,
    Fixture,
    Gameweek,
    LeagueStanding,
    LinkedTeam,
    LinkedTeamLeague,
    Player,
    PlayerGwLive,
    PlayerGwPrediction,
    PlayerXg,
    PushSubscription,
    Team,
)
from fplguru_core.settings import get_settings
from fplguru_tools import (
    gw_calendar,
    pick_overpowered_xi,
    template_diff,
    template_xi,
    trends,
)

_MODEL_VERSION = "basic-v1"
_ADV_MODEL_VERSION = "adv-v1"


async def _resolve_model_version(db: AsyncSession, model: str = "auto") -> str:
    """Map a ?model= choice to a stored model_version. ``auto`` prefers the
    advanced tier when any adv-v1 prediction exists, else falls back to basic."""
    if model == "basic":
        return _MODEL_VERSION
    if model == "advanced":
        return _ADV_MODEL_VERSION
    has_adv = (await db.execute(
        select(PlayerGwPrediction.player_id)
        .where(PlayerGwPrediction.model_version == _ADV_MODEL_VERSION).limit(1)
    )).first()
    return _ADV_MODEL_VERSION if has_adv else _MODEL_VERSION


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


app = FastAPI(title="FPLGuru API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


async def _live_snapshot(db: AsyncSession) -> dict:
    gw = (await db.execute(select(Gameweek).where(Gameweek.is_current))).scalar_one_or_none()
    if gw is None:
        gw = (await db.execute(select(Gameweek).where(Gameweek.is_next))).scalar_one_or_none()
    if gw is None:
        return {"gameweek_id": None, "updated_at": None, "fixtures": [], "players": []}

    fx = (await db.execute(
        select(Fixture).where(Fixture.gameweek_id == gw.id)
        .order_by(Fixture.kickoff_time, Fixture.id)
    )).scalars().all()
    paired = (await db.execute(
        select(PlayerGwLive, Player)
        .join(Player, Player.id == PlayerGwLive.player_id)
        .where(PlayerGwLive.gameweek_id == gw.id)
        .order_by(PlayerGwLive.total_points.desc(), PlayerGwLive.bps.desc())
    )).all()
    updated = max((lv.updated_at for lv, _ in paired), default=None)
    return {
        "gameweek_id": gw.id,
        "updated_at": updated.isoformat() if updated else None,
        "fixtures": [
            {"id": f.id, "home_team_id": f.home_team_id, "away_team_id": f.away_team_id,
             "home_score": f.home_score, "away_score": f.away_score,
             "started": f.started, "finished": f.finished, "minutes": f.minutes}
            for f in fx
        ],
        "players": [
            {"player_id": lv.player_id, "web_name": p.web_name, "team_id": p.team_id,
             "position": p.position, "minutes": lv.minutes, "live_points": lv.live_points,
             "bps": lv.bps, "projected_bonus": lv.projected_bonus,
             "total_points": lv.total_points}
            for lv, p in paired
        ],
    }


@app.get("/gameweeks/current/live")
async def live_snapshot(db: AsyncSession = Depends(get_db)) -> dict:
    return await _live_snapshot(db)


async def _live_event_stream(request: Request, poll_seconds: float) -> AsyncIterator[str]:
    sentinel = object()
    last: object = sentinel
    while True:
        async with get_sessionmaker()() as db:
            snap = await _live_snapshot(db)
        if snap["updated_at"] != last:
            last = snap["updated_at"]
            yield f"data: {json.dumps(snap)}\n\n"
        else:
            yield ": keepalive\n\n"
        await asyncio.sleep(poll_seconds)
        if await request.is_disconnected():
            break


@app.get("/gameweeks/current/live/stream")
async def live_stream(request: Request) -> StreamingResponse:
    poll_seconds = get_settings().live_stream_poll_seconds
    return StreamingResponse(
        _live_event_stream(request, poll_seconds),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/status")
async def status(db: AsyncSession = Depends(get_db)) -> dict:
    sources: dict[str, dict] = {}
    known = {"fpl_bootstrap", "fpl_fixtures", "live_poll", "pitch_xg"}
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
                  model: str = Query("auto", pattern="^(auto|basic|advanced)$"),
                  db: AsyncSession = Depends(get_db)) -> list[dict]:
    mv = await _resolve_model_version(db, model)
    rows = (await db.execute(
        select(PlayerGwPrediction, Player)
        .join(Player, Player.id == PlayerGwPrediction.player_id)
        .where(PlayerGwPrediction.model_version == mv,
               PlayerGwPrediction.horizon_gw <= horizon)
    )).all()
    agg: dict[int, dict] = {}
    for pred, player in rows:
        d = agg.setdefault(player.id, {
            "player_id": player.id, "web_name": player.web_name,
            "position": player.position, "now_cost": player.now_cost,
            "xp_total": 0.0, "model": mv,
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
        mv = await _resolve_model_version(db)
        for pid, total in (await db.execute(
            select(PlayerGwPrediction.player_id, func.sum(PlayerGwPrediction.xp))
            .where(PlayerGwPrediction.player_id.in_(pids),
                   PlayerGwPrediction.model_version == mv)
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


class _SeenBody(BaseModel):
    ids: list[int] | None = None


class _SettingsBody(BaseModel):
    alert_cap: int | None = None
    reminder_offsets: list[int] | None = None


def _clean_offsets(raw: list[int]) -> list[int]:
    vals = sorted({int(o) for o in raw if 0 < int(o) <= 4320}, reverse=True)
    return vals[:7]


def _alert_json(a: Alert) -> dict:
    return {
        "id": a.id, "type": a.type, "gameweek_id": a.gameweek_id,
        "player_id": a.player_id, "priority": a.priority, "title": a.title,
        "body": a.body, "payload": a.payload, "suppressed": a.suppressed,
        "seen": a.seen_at is not None, "created_at": a.updated_at.isoformat(),
    }


@app.get("/entries/{entry_id}/alerts")
async def entry_alerts(
    entry_id: int,
    include_suppressed: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> dict:
    lt = await _linked_or_404(db, entry_id)
    q = select(Alert).where(Alert.linked_team_id == lt.id)
    if not include_suppressed:
        q = q.where(Alert.suppressed.is_(False))
    rows = (await db.execute(
        q.order_by(Alert.priority.desc(), Alert.id.desc())
    )).scalars().all()
    unseen = sum(1 for a in rows if a.seen_at is None and not a.suppressed)
    return {"alerts": [_alert_json(a) for a in rows], "unseen": unseen}


@app.post("/entries/{entry_id}/alerts/seen")
async def mark_alerts_seen(
    entry_id: int, body: _SeenBody, db: AsyncSession = Depends(get_db)
) -> dict:
    lt = await _linked_or_404(db, entry_id)
    q = select(Alert).where(Alert.linked_team_id == lt.id, Alert.seen_at.is_(None))
    if body.ids:
        q = q.where(Alert.id.in_(body.ids))
    else:
        q = q.where(Alert.suppressed.is_(False))  # "mark all" == the visible feed
    rows = (await db.execute(q)).scalars().all()
    for a in rows:
        a.seen_at = func.now()
    await db.commit()
    return {"marked": len(rows)}


@app.get("/entries/{entry_id}/settings")
async def get_entry_settings(entry_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    lt = await _linked_or_404(db, entry_id)
    return {
        "fpl_entry_id": lt.fpl_entry_id,
        "alert_cap": lt.alert_cap,
        "reminder_offsets": lt.reminder_offsets or list(DEFAULT_REMINDER_OFFSETS),
    }


@app.patch("/entries/{entry_id}/settings")
async def patch_entry_settings(
    entry_id: int, body: _SettingsBody, db: AsyncSession = Depends(get_db)
) -> dict:
    lt = await _linked_or_404(db, entry_id)
    lt.alert_cap = body.alert_cap
    if body.reminder_offsets is not None:
        lt.reminder_offsets = _clean_offsets(body.reminder_offsets)
    result = {
        "fpl_entry_id": lt.fpl_entry_id,
        "alert_cap": body.alert_cap,
        "reminder_offsets": lt.reminder_offsets or list(DEFAULT_REMINDER_OFFSETS),
    }
    await db.commit()
    return result


class _PushKeys(BaseModel):
    p256dh: str
    auth: str


class _PushSubBody(BaseModel):
    endpoint: str
    keys: _PushKeys


class _PushUnsubBody(BaseModel):
    endpoint: str


@app.get("/push/vapid-public-key")
async def vapid_public_key() -> dict:
    return {"key": get_settings().vapid_public_key}


@app.post("/entries/{entry_id}/push/subscribe")
async def push_subscribe(entry_id: int, body: _PushSubBody,
                         db: AsyncSession = Depends(get_db)) -> dict:
    lt = await _linked_or_404(db, entry_id)
    existing = (await db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )).scalar_one_or_none()
    if existing is None:
        db.add(PushSubscription(linked_team_id=lt.id, endpoint=body.endpoint,
                                p256dh=body.keys.p256dh, auth=body.keys.auth))
    else:
        existing.linked_team_id = lt.id
        existing.p256dh = body.keys.p256dh
        existing.auth = body.keys.auth
    await db.commit()
    return {"ok": True}


@app.delete("/entries/{entry_id}/push/subscribe")
async def push_unsubscribe(entry_id: int, body: _PushUnsubBody,
                           db: AsyncSession = Depends(get_db)) -> dict:
    lt = await _linked_or_404(db, entry_id)
    rows = (await db.execute(
        select(PushSubscription).where(
            PushSubscription.linked_team_id == lt.id,
            PushSubscription.endpoint == body.endpoint,
        )
    )).scalars().all()
    for r in rows:
        await db.delete(r)
    await db.commit()
    return {"removed": len(rows)}


def _delta(rank: int | None, last: int | None) -> int | None:
    if rank is None or last is None or last == 0:
        return None
    return last - rank        # positive = moved up


@app.get("/entries/{entry_id}/leagues")
async def entry_leagues(entry_id: int, db: AsyncSession = Depends(get_db)) -> list[dict]:
    lt = await _linked_or_404(db, entry_id)
    rows = (await db.execute(
        select(LinkedTeamLeague).where(LinkedTeamLeague.linked_team_id == lt.id)
        .order_by(LinkedTeamLeague.entry_rank.is_(None), LinkedTeamLeague.entry_rank)
    )).scalars().all()
    return [
        {"league_id": r.league_id, "league_name": r.league_name,
         "entry_rank": r.entry_rank, "entry_last_rank": r.entry_last_rank,
         "delta": _delta(r.entry_rank, r.entry_last_rank)}
        for r in rows
    ]


@app.get("/leagues/{league_id}/standings")
async def league_standings(league_id: int, limit: int = Query(50, ge=1, le=200),
                           db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(
        select(LeagueStanding).where(LeagueStanding.league_id == league_id)
        .order_by(LeagueStanding.rank).limit(limit)
    )).scalars().all()
    return {
        "league_id": league_id,
        "standings": [
            {"entry_id": r.entry_id, "entry_name": r.entry_name, "player_name": r.player_name,
             "rank": r.rank, "last_rank": r.last_rank, "total": r.total,
             "event_total": r.event_total, "delta": _delta(r.rank, r.last_rank)}
            for r in rows
        ],
    }


@app.get("/leagues/{league_id}/search")
async def league_search(league_id: int, q: str = Query(..., min_length=1),
                        db: AsyncSession = Depends(get_db)) -> list[dict]:
    like = f"%{q}%"
    rows = (await db.execute(
        select(LeagueStanding).where(
            LeagueStanding.league_id == league_id,
            LeagueStanding.entry_name.ilike(like) | LeagueStanding.player_name.ilike(like),
        ).order_by(LeagueStanding.rank).limit(25)
    )).scalars().all()
    return [
        {"entry_id": r.entry_id, "entry_name": r.entry_name, "player_name": r.player_name,
         "rank": r.rank, "total": r.total}
        for r in rows
    ]


@app.get("/entries/{entry_id}/rank-history")
async def entry_rank_history(entry_id: int, db: AsyncSession = Depends(get_db)) -> list[dict]:
    lt = await _linked_or_404(db, entry_id)
    rows = (await db.execute(
        select(EntryGwHistory).where(EntryGwHistory.linked_team_id == lt.id)
        .order_by(EntryGwHistory.gameweek_id)
    )).scalars().all()
    return [
        {"gameweek_id": r.gameweek_id, "overall_rank": r.overall_rank,
         "points": r.points, "total_points": r.total_points}
        for r in rows
    ]


def _template_rationale(pick: dict, kind: str, horizon: int) -> str:
    scope = "your XI" if kind == "constrained" else "all players"
    return (f"{pick['web_name']} ({pick['team_short']}) tops {scope} on projected points "
            f"({pick['xp']}) over the next {horizon} gameweek(s).")


async def _rationale_for(db: AsyncSession, gw_id: int, pick: dict, alts: list[dict], *,
                         kind: str, horizon: int) -> tuple[str, str]:
    cached = (await db.execute(
        select(CaptainRationale).where(
            CaptainRationale.player_id == pick["player_id"],
            CaptainRationale.gameweek_id == gw_id,
            CaptainRationale.kind == kind,
        )
    )).scalar_one_or_none()
    if cached is not None:
        return cached.text, "llm"
    text = await generate_within_budget(
        db, "captain", rationale_prompt(pick, alts, kind=kind, horizon=horizon),
        max_output_tokens=160,
    )
    if text:
        db.add(CaptainRationale(player_id=pick["player_id"], gameweek_id=gw_id, kind=kind,
                                text=text, model=get_settings().gemini_model))
        await db.commit()
        return text, "llm"
    return _template_rationale(pick, kind, horizon), "template"


@app.get("/entries/{entry_id}/captain")
async def entry_captain(entry_id: int, horizon: int = Query(3, ge=1, le=5),
                        db: AsyncSession = Depends(get_db)) -> dict:
    lt = await _linked_or_404(db, entry_id)
    gw = (await db.execute(select(Gameweek).where(Gameweek.is_current))).scalar_one_or_none()
    if gw is None:
        gw = (await db.execute(select(Gameweek).where(Gameweek.is_next))).scalar_one_or_none()
    gw_id = gw.id if gw else 0

    xp_by_player = dict((await db.execute(
        select(PlayerGwPrediction.player_id, func.sum(PlayerGwPrediction.xp))
        .where(PlayerGwPrediction.model_version == await _resolve_model_version(db),
               PlayerGwPrediction.horizon_gw <= horizon)
        .group_by(PlayerGwPrediction.player_id)
    )).all())

    players = (await db.execute(
        select(Player, Team.short_name).join(Team, Team.id == Player.team_id)
    )).all()
    all_players = [
        {"player_id": p.id, "web_name": p.web_name, "position": p.position,
         "team_short": short, "xp": float(xp_by_player.get(p.id, 0.0))}
        for p, short in players
        if p.id in xp_by_player
    ]

    pick_gw = (await db.execute(
        select(func.max(EntryPick.gameweek_id)).where(EntryPick.linked_team_id == lt.id)
    )).scalar()
    pick_rows = (await db.execute(
        select(EntryPick.player_id, EntryPick.multiplier)
        .where(EntryPick.linked_team_id == lt.id, EntryPick.gameweek_id == pick_gw)
    )).all()
    xi_ids = {pid for pid, mult in pick_rows if mult > 0}
    squad_ids = {pid for pid, _ in pick_rows}
    by_id = {p["player_id"]: p for p in all_players}
    squad = [
        {**by_id[pid], "in_xi": pid in xi_ids}
        for pid in squad_ids if pid in by_id
    ]

    ranked = rank_captains(squad, all_players, top=5)
    rationale: dict[str, str] = {}
    source = "template"
    for kind in ("constrained", "unconstrained"):
        picks = ranked[kind]
        if not picks:
            rationale[kind] = "No candidates — link a full squad and wait for predictions."
            continue
        text, src = await _rationale_for(db, gw_id, picks[0], picks[1:], kind=kind,
                                         horizon=horizon)
        rationale[kind] = text
        if src == "llm":
            source = "llm"
    return {"gameweek_id": gw_id, "horizon": horizon, **ranked,
            "rationale": rationale, "rationale_source": source}


def _player_dicts(rows: list[Player]) -> list[dict]:
    return [
        {"player_id": p.id, "web_name": p.web_name, "position": p.position,
         "team_id": p.team_id, "now_cost": p.now_cost,
         "selected_by_percent": p.selected_by_percent,
         "transfers_in_event": p.transfers_in_event,
         "transfers_out_event": p.transfers_out_event,
         "cost_change_event": p.cost_change_event}
        for p in rows
    ]


@app.get("/trends")
async def gw_trends(limit: int = Query(10, ge=1, le=50),
                    db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(Player))).scalars().all()
    return trends(_player_dicts(rows), limit=limit)


@app.get("/template")
async def template(db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(Player))).scalars().all()
    return template_xi(_player_dicts(rows))


@app.get("/entries/{entry_id}/template-diff")
async def template_diff_for_entry(entry_id: int,
                                  db: AsyncSession = Depends(get_db)) -> dict:
    lt = await _linked_or_404(db, entry_id)
    tmpl = template_xi(_player_dicts((await db.execute(select(Player))).scalars().all()))
    pick_gw = (await db.execute(
        select(func.max(EntryPick.gameweek_id)).where(EntryPick.linked_team_id == lt.id)
    )).scalar()
    picks = (await db.execute(
        select(EntryPick.player_id).where(EntryPick.linked_team_id == lt.id,
                                          EntryPick.gameweek_id == pick_gw)
    )).scalars().all()
    return {"template": tmpl, **template_diff([{"player_id": p} for p in picks], tmpl)}


@app.get("/calendar")
async def calendar(from_gw: int = Query(..., ge=1, le=38),
                   to_gw: int = Query(..., ge=1, le=38),
                   db: AsyncSession = Depends(get_db)) -> list[dict]:
    team_ids = [t for (t,) in (await db.execute(select(Team.id))).all()]
    fixtures = [
        {"gameweek_id": f.gameweek_id, "home_team_id": f.home_team_id,
         "away_team_id": f.away_team_id}
        for f in (await db.execute(select(Fixture))).scalars().all()
    ]
    gws = [{"id": g.id} for g in (await db.execute(select(Gameweek))).scalars().all()]
    return gw_calendar(fixtures, gws, from_gw=from_gw, to_gw=to_gw, team_ids=team_ids)


@app.get("/overpowered")
async def overpowered(horizon: int = Query(5, ge=1, le=10),
                      db: AsyncSession = Depends(get_db)) -> dict:
    xp_by_player = dict((await db.execute(
        select(PlayerGwPrediction.player_id, func.sum(PlayerGwPrediction.xp))
        .where(PlayerGwPrediction.model_version == await _resolve_model_version(db),
               PlayerGwPrediction.horizon_gw <= horizon)
        .group_by(PlayerGwPrediction.player_id)
    )).all())
    rows = (await db.execute(select(Player))).scalars().all()
    players = [
        {**pd, "xp": float(xp_by_player.get(pd["player_id"], 0.0))}
        for pd in _player_dicts(rows)
        if pd["player_id"] in xp_by_player
    ]
    return pick_overpowered_xi(players)


def _xg_row(r: PlayerXg) -> dict:
    return {"gameweek_id": r.gameweek_id, "fixture_id": r.fixture_id, "minutes": r.minutes,
            "xg": r.xg, "xg_ot": r.xg_ot, "xag": r.xag, "key_passes": r.key_passes,
            "chances_created": r.chances_created, "vaep": r.vaep}


@app.get("/players/{player_id}/xg")
async def player_xg(player_id: int, last: int = Query(6, ge=1, le=38),
                    db: AsyncSession = Depends(get_db)) -> dict:
    player = (await db.execute(
        select(Player).where(Player.id == player_id))).scalar_one_or_none()
    rows = (await db.execute(
        select(PlayerXg).where(PlayerXg.player_id == player_id)
        .order_by(PlayerXg.gameweek_id.desc(), PlayerXg.fixture_id.desc())
        .limit(last)
    )).scalars().all()
    if player is None or not rows:
        raise HTTPException(status_code=404, detail="no xg for player")
    tot = {k: round(sum(getattr(r, k) for r in rows), 3) for k in ("xg", "xg_ot", "xag")}
    tot["minutes"] = sum(r.minutes for r in rows)
    return {"player_id": player.id, "web_name": player.web_name, "position": player.position,
            "totals": tot, "per_gw": [_xg_row(r) for r in rows]}


@app.get("/xg-snapshot")
async def xg_snapshot(last: int = Query(6, ge=1, le=15),
                      position: str | None = Query(None),
                      db: AsyncSession = Depends(get_db)) -> dict:
    max_gw = (await db.execute(select(func.max(PlayerXg.gameweek_id)))).scalar()
    if max_gw is None:
        return {"from_gw": None, "players": []}
    lo = max_gw - last + 1
    q = (
        select(Player, func.sum(PlayerXg.xg), func.sum(PlayerXg.xag),
               func.sum(PlayerXg.minutes))
        .join(PlayerXg, PlayerXg.player_id == Player.id)
        .where(PlayerXg.gameweek_id >= lo)
        .group_by(Player.id)
    )
    if position:
        q = q.where(Player.position == position)
    rows = (await db.execute(q)).all()
    players = sorted(
        ({"player_id": p.id, "web_name": p.web_name, "position": p.position,
          "team_id": p.team_id, "xg": round(float(xg or 0), 2),
          "xag": round(float(xa or 0), 2), "minutes": int(mins or 0)}
         for p, xg, xa, mins in rows),
        key=lambda d: d["xg"] + d["xag"], reverse=True,
    )
    return {"from_gw": lo, "players": players}


@app.get("/players/{player_id}/xp")
async def player_xp(player_id: int, horizon: int = Query(5, ge=1, le=5),
                    model: str = Query("auto", pattern="^(auto|basic|advanced)$"),
                    db: AsyncSession = Depends(get_db)) -> dict:
    mv = await _resolve_model_version(db, model)
    player = (await db.execute(
        select(Player).where(Player.id == player_id)
    )).scalar_one_or_none()
    preds = (await db.execute(
        select(PlayerGwPrediction)
        .where(PlayerGwPrediction.player_id == player_id,
               PlayerGwPrediction.model_version == mv,
               PlayerGwPrediction.horizon_gw <= horizon)
        .order_by(PlayerGwPrediction.horizon_gw)
    )).scalars().all()
    if player is None or not preds:
        raise HTTPException(status_code=404, detail="no predictions for player")
    return {
        "player_id": player.id, "web_name": player.web_name, "position": player.position,
        "model": mv,
        "xp_total": float(sum(p.xp for p in preds)),
        "per_gw": [
            {"horizon_gw": p.horizon_gw, "gameweek_id": p.gameweek_id, "xp": p.xp,
             "floor": p.xp_floor, "ceiling": p.xp_ceiling,
             "x_minutes": p.x_minutes, "x_goals": p.x_goals, "x_assists": p.x_assists,
             "x_cs_or_gc": p.x_cs_or_gc, "x_bonus": p.x_bonus}
            for p in preds
        ],
    }
