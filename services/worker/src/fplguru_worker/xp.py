"""Assemble xP features from the live DB and upsert player_gw_predictions.

Two model tiers are written when their artifacts are present:
- ``basic-v1``  : linear per-position ridge, total only (component x_* fields 0.0).
- ``adv-v1``    : per-position GBRT with quantile floor/ceiling bands, plus an
  approximate component split (see ``_component_split``).

The advanced tier's expected-goals features (form_xg_5 etc.) are 0.0 until a
PitchAPI key populates ``player_xg`` with an FPL id mapping; the GBRT then still
predicts from the nine shared FPL features. See ``_adv_feature_row``.
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
from fplguru_ml.model_advanced import AdvancedXP
from fplguru_ml.model_basic import BasicXP
from fplguru_ml.rollout import band_halfwidth, project_horizon
from fplguru_ml.serving import to_adv_row

logger = logging.getLogger("fplguru.worker")

_ZERO_COMPONENTS = {"x_minutes": 0.0, "x_goals": 0.0, "x_assists": 0.0,
                    "x_cs_or_gc": 0.0, "x_bonus": 0.0}


def _artifact_dir() -> str:
    return os.environ.get("FPLGURU_XP_ARTIFACT_DIR", get_settings().xp_artifact_dir)


def _adv_artifact_dir() -> str:
    return os.environ.get("FPLGURU_ADV_XP_ARTIFACT_DIR",
                          get_settings().adv_xp_artifact_dir)


def _load_adv() -> AdvancedXP | None:
    try:
        return AdvancedXP.load(_adv_artifact_dir())
    except (FileNotFoundError, NotADirectoryError):
        return None


def _component_split(position: str, fr: dict, xp: float) -> dict:
    """Approximate x_* breakdown for the UI. NOT a calibrated component model —
    a heuristic decomposition of the GBRT total; real component models are a
    deferred P2b follow-up."""
    x_minutes = max(0.0, min(90.0, float(fr.get("starts_rate_5", 0.0)) * 90.0))
    appearance = 2.0 if x_minutes >= 60.0 else (1.0 if x_minutes > 0 else 0.0)
    attack = max(0.0, xp - appearance)
    g5 = float(fr.get("form_goals_5", 0.0))
    a5 = float(fr.get("form_assists_5", 0.0))
    goal_share = g5 / (g5 + a5) if (g5 + a5) > 0 else 0.6
    x_goals = attack * goal_share * 0.7
    x_assists = attack * (1.0 - goal_share) * 0.3
    cs_weight = {"GK": 1.0, "DEF": 0.9, "MID": 0.3, "FWD": 0.05}.get(position, 0.2)
    x_cs_or_gc = max(0.0, cs_weight * (1.6 - 0.4 * float(fr.get("form_xgc_5", 0.0))))
    x_bonus = 0.12 * xp
    return {"x_minutes": round(x_minutes, 3), "x_goals": round(x_goals, 3),
            "x_assists": round(x_assists, 3), "x_cs_or_gc": round(x_cs_or_gc, 3),
            "x_bonus": round(x_bonus, 3)}


async def _upsert_predictions(session, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(PlayerGwPrediction).values(rows)
    keys = ("player_id", "gameweek_id", "model_version")
    update_cols = {c: stmt.excluded[c] for c in rows[0] if c not in keys}
    update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(index_elements=list(keys), set_=update_cols)
    await session.execute(stmt)


def _feature_plan(p, h, side, conceded, future_gws):
    """Return (triples, fallbacks) for one player:
    triples   = list[(horizon_gw, gameweek_id, basic_feature_row)]
    fallbacks = list[(horizon_gw, gameweek_id)]  -- thin history / unbuildable
    """
    triples: list[tuple[int, int, dict]] = []
    fallbacks: list[tuple[int, int]] = []
    for hz, g in enumerate(future_gws, start=1):
        sd = side.get((g.id, p.team_id))
        if sd is None:
            continue  # blank gameweek for this team
        was_home, opp = sd
        opp_vals = conceded.get((opp, p.position), [])
        fr = None
        if len(h) >= 3:
            fr = feature_row_from_history(
                h[-5:], was_home=was_home, value=p.now_cost,
                opp_conceded_to_pos_5=(wmean(opp_vals[-5:], 5) if opp_vals else 0.0),
            )
        if fr is None:
            fallbacks.append((hz, g.id))
        else:
            triples.append((hz, g.id, fr))
    return triples, fallbacks


async def compute_and_store_xp(horizon: int = 5) -> int:
    started = datetime.now(UTC)
    model = BasicXP.load(_artifact_dir())
    adv = _load_adv()
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
        n_adv = 0
        for p in players:
            h = history.get(p.id, [])
            triples, fallbacks = _feature_plan(p, h, side, conceded, future_gws)

            if triples:
                proj = project_horizon(p.position, [t[2] for t in triples], model)
                for (hz, gw_id, _), gp in zip(triples, proj.per_gw, strict=False):
                    rows.append({
                        "player_id": p.id, "gameweek_id": gw_id, "horizon_gw": hz,
                        "model_version": model.version, "xp": gp.xp,
                        **_ZERO_COMPONENTS,
                        "xp_floor": gp.floor, "xp_ceiling": gp.ceiling,
                    })
                    n_real += 1

            for hz, gw_id in fallbacks:
                xp = model.baseline(p.position)
                half = band_halfwidth(hz)
                rows.append({
                    "player_id": p.id, "gameweek_id": gw_id, "horizon_gw": hz,
                    "model_version": model.version, "xp": xp,
                    **_ZERO_COMPONENTS,
                    "xp_floor": xp - half, "xp_ceiling": xp + half,
                })
                n_fallback += 1

            if adv is None:
                continue

            if triples:
                adv_rows_in = [to_adv_row(t[2]) for t in triples]
                mids = adv.predict_rows(p.position, adv_rows_in)
                lows, highs = adv.predict_bands(p.position, adv_rows_in)
                for (hz, gw_id, fr), xp, lo, hi in zip(
                    triples, mids, lows, highs, strict=False
                ):
                    rows.append({
                        "player_id": p.id, "gameweek_id": gw_id, "horizon_gw": hz,
                        "model_version": adv.version, "xp": float(xp),
                        **_component_split(p.position, fr, float(xp)),
                        "xp_floor": max(0.0, float(lo)), "xp_ceiling": float(hi),
                    })
                    n_adv += 1
            for hz, gw_id in fallbacks:
                xp = adv.baseline(p.position)
                half = band_halfwidth(hz)
                rows.append({
                    "player_id": p.id, "gameweek_id": gw_id, "horizon_gw": hz,
                    "model_version": adv.version, "xp": xp,
                    **_ZERO_COMPONENTS,
                    "xp_floor": max(0.0, xp - half), "xp_ceiling": xp + half,
                })
                n_adv += 1

        await _upsert_predictions(session, rows)
        session.add(DataSyncLog(
            source="xp_compute", status="ok",
            detail=f"{n_real} modelled + {n_fallback} cold-start + {n_adv} adv-v1",
            started_at=started, finished_at=datetime.now(UTC)))
    logger.info("xp computed: %d predictions over %d gameweeks", len(rows), len(future_gws))
    return len(rows)
