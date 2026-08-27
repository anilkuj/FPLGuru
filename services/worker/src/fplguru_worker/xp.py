"""Assemble Basic-xP features from the live DB and upsert player_gw_predictions.

Component fields (x_minutes/x_goals/...) are left 0.0 — the linear Basic model
produces only a total. They are populated in the Advanced tier (sub-plan P2b).
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from fplguru_core.db import get_sessionmaker
from fplguru_core.models import (
    DataSyncLog,
    Fixture,
    Gameweek,
    Player,
    PlayerGwPrediction,
    PlayerGwStat,
)
from fplguru_core.settings import get_settings
from fplguru_ml.features import feature_row_from_history, wmean
from fplguru_ml.model_basic import BasicXP
from fplguru_ml.rollout import band_halfwidth, project_horizon

logger = logging.getLogger("fplguru.worker")


def _artifact_dir() -> str:
    return os.environ.get("FPLGURU_XP_ARTIFACT_DIR", get_settings().xp_artifact_dir)


async def _upsert_predictions(session, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(PlayerGwPrediction).values(rows)
    keys = ("player_id", "gameweek_id", "model_version")
    update_cols = {c: stmt.excluded[c] for c in rows[0] if c not in keys}
    update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(index_elements=list(keys), set_=update_cols)
    await session.execute(stmt)


async def compute_and_store_xp(horizon: int = 5) -> int:
    started = datetime.now(UTC)
    model = BasicXP.load(_artifact_dir())
    async with get_sessionmaker()() as session, session.begin():
        future_gws = (await session.execute(
            select(Gameweek).where(Gameweek.finished.is_(False))
            .order_by(Gameweek.deadline_time).limit(horizon)
        )).scalars().all()
        if not future_gws:
            session.add(DataSyncLog(source="xp_compute", status="ok",
                                    detail="no future gameweeks",
                                    started_at=started, finished_at=datetime.now(UTC)))
            return 0

        players = (await session.execute(
            select(Player).where(Player.status == "a")
        )).scalars().all()
        players_by_id = {p.id: p for p in (await session.execute(select(Player))).scalars().all()}

        stats = (await session.execute(
            select(PlayerGwStat).join(Gameweek, Gameweek.id == PlayerGwStat.gameweek_id)
            .where(Gameweek.finished.is_(True)).order_by(PlayerGwStat.gameweek_id)
        )).scalars().all()

        history: dict[int, list[dict]] = {}
        conceded: dict[tuple[int, str], list[float]] = {}
        for s in stats:
            if s.minutes > 0:
                history.setdefault(s.player_id, []).append(
                    {"total_points": s.total_points, "minutes": s.minutes,
                     "goals": s.goals, "assists": s.assists}
                )
            p = players_by_id.get(s.player_id)
            if s.opponent_team_id is not None and p is not None:
                conceded.setdefault((s.opponent_team_id, p.position), []).append(
                    float(s.total_points)
                )

        fut_ids = [g.id for g in future_gws]
        side: dict[tuple[int, int], tuple[bool, int]] = {}
        for f in (await session.execute(
            select(Fixture).where(Fixture.gameweek_id.in_(fut_ids))
        )).scalars().all():
            side[(f.gameweek_id, f.home_team_id)] = (True, f.away_team_id)
            side[(f.gameweek_id, f.away_team_id)] = (False, f.home_team_id)

        rows: list[dict] = []
        n_real = 0
        n_fallback = 0
        for p in players:
            h = history.get(p.id, [])
            triples: list[tuple[int, int, dict]] = []   # (horizon_gw, gameweek_id, feature_row)
            fallbacks: list[tuple[int, int]] = []       # (horizon_gw, gameweek_id)
            for hz, g in enumerate(future_gws, start=1):
                sd = side.get((g.id, p.team_id))
                if sd is None:
                    continue   # blank gameweek for this team
                was_home, opp = sd
                opp_vals = conceded.get((opp, p.position), [])
                fr = None
                if len(h) >= 3:
                    fr = feature_row_from_history(
                        h[-5:], was_home=was_home, value=p.now_cost,
                        opp_conceded_to_pos_5=(wmean(opp_vals[-5:], 5) if opp_vals else 0.0),
                    )
                if fr is None:
                    fallbacks.append((hz, g.id))   # thin history OR unbuildable row
                else:
                    triples.append((hz, g.id, fr))

            if triples:
                proj = project_horizon(p.position, [t[2] for t in triples], model)
                for (hz, gw_id, _), gp in zip(triples, proj.per_gw, strict=False):
                    rows.append({
                        "player_id": p.id, "gameweek_id": gw_id, "horizon_gw": hz,
                        "model_version": model.version, "xp": gp.xp,
                        "x_minutes": 0.0, "x_goals": 0.0, "x_assists": 0.0,
                        "x_cs_or_gc": 0.0, "x_bonus": 0.0,
                        "xp_floor": gp.floor, "xp_ceiling": gp.ceiling,
                    })
                    n_real += 1

            for hz, gw_id in fallbacks:
                xp = model.baseline(p.position)
                half = band_halfwidth(hz)
                rows.append({
                    "player_id": p.id, "gameweek_id": gw_id, "horizon_gw": hz,
                    "model_version": model.version, "xp": xp,
                    "x_minutes": 0.0, "x_goals": 0.0, "x_assists": 0.0,
                    "x_cs_or_gc": 0.0, "x_bonus": 0.0,
                    "xp_floor": xp - half, "xp_ceiling": xp + half,
                })
                n_fallback += 1

        await _upsert_predictions(session, rows)
        session.add(DataSyncLog(source="xp_compute", status="ok",
                                detail=f"{n_real} modelled + {n_fallback} cold-start",
                                started_at=started, finished_at=datetime.now(UTC)))
    logger.info("xp computed: %d predictions over %d gameweeks", len(rows), len(future_gws))
    return len(rows)
