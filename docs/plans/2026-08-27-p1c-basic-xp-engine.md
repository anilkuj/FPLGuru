# P1c — Basic xP Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Predict expected FPL points (xP) for every player over a 1–5 gameweek horizon using a transparent per-position linear model trained on historical data, with a walk-forward backtest reporting MAE/RMSE per position, served through the worker into a `player_gw_predictions` table and exposed on the API.

**Architecture:** Three pure, DB-free layers in `packages/ml` — **feature builders** (produce the same numeric feature vector from either a historical training frame or live DB entities), a **ridge model** (closed-form `(XᵀX + λI)⁻¹Xᵀy`, one per position group, serialized as plain JSON — no scikit-learn, no joblib), and a **walk-forward backtest**. A new `player_gw_stats` table + `event/{gw}/live` ingest supplies per-GW actuals (the rolling-form inputs Foundation didn't store). A worker task computes and upserts predictions; two API endpoints read them.

**Tech Stack:** Python 3.12, numpy (pinned `<2.5` — Smart App Control blocks 2.5.x), pandas (`<4`), SQLAlchemy 2.0 async, Alembic, Celery, FastAPI, pytest. **No scikit-learn / joblib** — the Basic model is hand-rolled ridge so it has no native-binary surface for SAC to block; scikit-learn arrives with the Advanced GBM in sub-plan P2b.

**Reference:** Master plan [`2026-08-27-fplguru-master-build-plan.md`](2026-08-27-fplguru-master-build-plan.md) §5.2 (Basic tier), §5.3–5.5. Builds on Foundation ([`2026-08-27-foundation.md`](2026-08-27-foundation.md)) — branch `feature/basic-xp` off `main`.

---

## Context from Foundation (already built)

- `fplguru_core.models`: `Team` (has `strength_attack_home/away`, `strength_defence_home/away`, `strength_overall_home/away`), `Gameweek`, `Player` (`position` GK/DEF/MID/FWD, `now_cost`, `status`, `total_points` = *season* total), `Fixture` (`gameweek_id`, `home_team_id`, `away_team_id`, `home_difficulty`, `away_difficulty`, `finished`), `DataSyncLog`. `Base.metadata` has a `naming_convention`.
- `fplguru_core.db`: `get_sessionmaker()`, `session_scope()` (asynccontextmanager), `dispose_engine()`, `reset_state()`.
- `fplguru_core.settings.get_settings()` → `fpl_api_base`, `database_url`, …
- `fplguru_core.constants.POSITION_BY_ELEMENT_TYPE = {1:"GK",2:"DEF",3:"MID",4:"FWD"}`.
- `fplguru_fpl_client.FplClient` — async, `bootstrap_static()`, `fixtures()`; add `event_live(gw)` in Task 3.
- `fplguru_ingest.fpl` — `normalize_teams/gameweeks/players/fixtures`.
- `fplguru_ingest.historical.normalize_merged_gw(csv_path, season) -> list[dict]` with keys: `season, player_name, position, team, gameweek, minutes, goals, assists, clean_sheet, total_points, xg, xa, was_home, opponent_team_id, value`. `scripts/fetch_historical.py` downloads vaastav `merged_gw.csv` per season to `data/historical/` (gitignored).
- `services/worker/tasks.py`: `_upsert(session, model, rows) -> int` (pg `ON CONFLICT (id)` upsert), `_record(...)`, `_log_error(...)`, `_run_and_dispose(coro_fn)`, Celery `sync_bootstrap`/`sync_fixtures` with a Beat schedule.
- `services/api/main.py`: `get_db` (read-only), `_gw`, endpoints `/health /ready /gameweeks /gameweeks/current /status`.
- Root `conftest.py`: `db_engine` (session, opt-in), `db_session` (function, truncate-after), autouse `_point_app_at_test_db`.

> **Test-seeding gotcha:** the models declare **no `relationship()`**, so a single `db_session.add_all([...])` with a mix of FK parents and children flushes mappers in *alphabetical class order* (`Fixture` before `Gameweek`, `Player` before `Team`) → `ForeignKeyViolationError`. **Seed in FK-parent-first waves**, each followed by `await db_session.commit()` (or `.flush()`): `Team`/`Gameweek` → `Player` → `Fixture`/`PlayerGwStat`/`PlayerGwPrediction`. Every test snippet below that seeds a parent+child mix must be split this way.
- Toolchain: `venv`+`pip`, `python -m <tool>`, commits staged `git add -A -- ':!docs'`, author `Anil Kujur <anilkuj@gmail.com>` + `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

---

## Feature set (Basic — FPL-data-only, leak-safe, available at both train and serve time)

Per player-GW, all computed from data strictly **before** the target GW:

| Feature | Definition |
|---|---|
| `form_points_3` | recency-weighted mean of `total_points` over the player's last 3 appearances (weights 3,2,1) |
| `form_points_5` | recency-weighted mean of `total_points` over last 5 (weights 5..1) |
| `form_minutes_3` | mean `minutes` over last 3 appearances |
| `starts_rate_5` | fraction of last 5 appearances with `minutes >= 60` |
| `form_goals_5` | mean `goals` per appearance over last 5 |
| `form_assists_5` | mean `assists` per appearance over last 5 |
| `was_home` | 1 if the target fixture is at home, else 0 |
| `value` | player price in tenths of a million at the target GW (`now_cost` live; `value` historical) |
| `opp_conceded_to_pos_5` | rolling mean of `total_points` that the opponent team conceded **to this player's position group** over the opponent's last 5 matches that season (leak-safe: only matches before the target GW) |

Target: `total_points` in the target GW. **One ridge model per position group** (GK/DEF/MID/FWD) — position itself is not a feature.

"Appearance" = a player-GW row with `minutes > 0`. Players with fewer than 3 prior appearances get NaN features → dropped from **training**; at **serve** time (`compute_xp`) they get a **cold-start fallback**: `xp = BasicXP.baseline(position)` (the training-set mean points for that position, else global mean) with a widening band. This keeps `/xp` populated for every active player from GW1. (Added in "Task 12b".)

---

## File structure

| Path | Responsibility |
|---|---|
| `packages/core/src/fplguru_core/models.py` (modify) | add `PlayerGwStat`, `PlayerGwFeature`, `PlayerGwPrediction` |
| `alembic/versions/0002_*.py` | migration for the 3 new tables |
| `packages/fpl_client/src/fplguru_fpl_client/client.py` (modify) | add `event_live(gw)` |
| `packages/ingest/src/fplguru_ingest/fpl.py` (modify) | add `normalize_event_live(gw, payload)` |
| `packages/ml/src/fplguru_ml/frame.py` | `build_training_frame(rows) -> pandas.DataFrame` (historical → features + target) |
| `packages/ml/src/fplguru_ml/features.py` | `FEATURE_NAMES`, `feature_row_from_history(history, target_ctx) -> dict` (live path; same keys as the frame) |
| `packages/ml/src/fplguru_ml/ridge.py` | `RidgeModel` (fit closed-form, predict, `to_json`/`from_json`) |
| `packages/ml/src/fplguru_ml/model_basic.py` | `train_basic(frame, alpha) -> BasicXP`; `BasicXP.predict_rows(pos, rows)`; `BasicXP.save(dir)`/`load(dir)`; per-position means fallback |
| `packages/ml/src/fplguru_ml/backtest.py` | `walk_forward(frame, alpha) -> BacktestResult`; `.metrics_by_position()` |
| `packages/ml/src/fplguru_ml/rollout.py` | `project_horizon(pos, per_gw_feature_rows, model) -> HorizonPrediction` (per-GW + cumulative + widening band) |
| `packages/ml/artifacts/basic/` | committed model JSON (small — coefs only), produced by `scripts/train_xp.py` |
| `scripts/train_xp.py` | load `data/historical/*.csv` → frame → train → save artifacts → print summary |
| `scripts/backtest_xp.py` | load historical → walk-forward → write `docs/xp-backtest/<date>.md` |
| `services/worker/src/fplguru_worker/tasks.py` (modify) | `sync_gw_stats`, `compute_xp` tasks + Beat entries |
| `services/api/src/fplguru_api/main.py` (modify) | `GET /xp`, `GET /players/{id}/xp` |

---

## Task 1: `packages/ml` dependencies + skeleton

**Files:**
- Modify: `packages/ml/pyproject.toml`
- Test: `packages/ml/tests/test_ml_smoke.py`

- [ ] **Step 1: Set deps**

`packages/ml/pyproject.toml` → `dependencies`:
```toml
dependencies = [
    "fplguru-core",
    "fplguru-ingest",
    "numpy>=2.2,<2.5",
    "pandas>=2.2,<4",
]
```
Add `-e ./packages/ml` is already in `requirements-dev.txt`. Run `python -m pip install -r requirements-dev.txt`.

- [ ] **Step 2: Failing test**

`packages/ml/tests/test_ml_smoke.py`:
```python
def test_imports():
    import fplguru_ml  # noqa: F401
    import numpy, pandas  # noqa: F401
```
Run: `python -m pytest packages/ml/tests/test_ml_smoke.py -v` → PASS (package already exists as a stub; this just asserts numpy/pandas resolve under the `<2.5` pin).

- [ ] **Step 3: Commit**

```bash
git add -A -- ':!docs'
git commit -m "feat(ml): add numpy/pandas deps to fplguru-ml"
```

---

## Task 2: Feature-store & stats models + migration

**Files:**
- Modify: `packages/core/src/fplguru_core/models.py`
- Test: `packages/core/tests/test_ml_models.py`
- Create: `alembic/versions/0002_ml_tables.py` (autogenerated)

- [ ] **Step 1: Write the failing test**

`packages/core/tests/test_ml_models.py`:
```python
from fplguru_core.models import Base, PlayerGwFeature, PlayerGwPrediction, PlayerGwStat


def test_ml_tables_registered():
    assert {"player_gw_stats", "player_gw_features", "player_gw_predictions"} <= set(Base.metadata.tables)


def test_stat_unique_on_player_gw():
    cols = {c.name for c in PlayerGwStat.__table__.columns}
    assert {"player_id", "gameweek_id", "minutes", "total_points", "goals", "assists", "clean_sheets"} <= cols
    uqs = [c for c in PlayerGwStat.__table__.constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert any({"player_id", "gameweek_id"} == {c.name for c in uq.columns} for uq in uqs)


def test_prediction_has_components_and_horizon():
    cols = {c.name for c in PlayerGwPrediction.__table__.columns}
    assert {"player_id", "gameweek_id", "horizon_gw", "model_version",
            "xp", "x_minutes", "x_goals", "x_assists", "x_cs_or_gc",
            "x_bonus", "xp_floor", "xp_ceiling"} <= cols


def test_feature_row_versioned():
    cols = {c.name for c in PlayerGwFeature.__table__.columns}
    assert {"player_id", "gameweek_id", "feature_set_version", "features"} <= cols
```

- [ ] **Step 2: Run → fails** (`ImportError` for the new names).

- [ ] **Step 3: Add models to `models.py`** (append after `DataSyncLog`):

```python
from sqlalchemy import JSON, Float, UniqueConstraint  # add to the existing sqlalchemy import line


class PlayerGwStat(_TimestampMixin, Base):
    """Actual per-player-per-gameweek scoring, from event/{gw}/live."""
    __tablename__ = "player_gw_stats"
    __table_args__ = (UniqueConstraint("player_id", "gameweek_id", name="uq_player_gw_stats_player_id_gameweek_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    clean_sheets: Mapped[int] = mapped_column(Integer, default=0)
    goals_conceded: Mapped[int] = mapped_column(Integer, default=0)
    bonus: Mapped[int] = mapped_column(Integer, default=0)
    was_home: Mapped[bool] = mapped_column(Boolean, default=False)
    opponent_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    value: Mapped[int] = mapped_column(Integer, default=0)  # price at that GW, tenths


class PlayerGwFeature(_TimestampMixin, Base):
    """Versioned feature vector for a player-GW (JSON blob keyed by FEATURE_NAMES)."""
    __tablename__ = "player_gw_features"
    __table_args__ = (UniqueConstraint("player_id", "gameweek_id", "feature_set_version",
                                       name="uq_player_gw_features_player_id_gameweek_id_feature_set_version"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    feature_set_version: Mapped[str] = mapped_column(String(16))
    features: Mapped[dict] = mapped_column(JSON)


class PlayerGwPrediction(_TimestampMixin, Base):
    """xP for a player in a future GW under a model version. One row per (player, gw, model_version)."""
    __tablename__ = "player_gw_predictions"
    __table_args__ = (UniqueConstraint("player_id", "gameweek_id", "model_version",
                                       name="uq_player_gw_predictions_player_id_gameweek_id_model_version"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    horizon_gw: Mapped[int] = mapped_column(Integer)  # 1 = next GW, ... 5
    model_version: Mapped[str] = mapped_column(String(32))
    xp: Mapped[float] = mapped_column(Float)
    x_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    x_goals: Mapped[float] = mapped_column(Float, default=0.0)
    x_assists: Mapped[float] = mapped_column(Float, default=0.0)
    x_cs_or_gc: Mapped[float] = mapped_column(Float, default=0.0)
    x_bonus: Mapped[float] = mapped_column(Float, default=0.0)
    xp_floor: Mapped[float] = mapped_column(Float, default=0.0)
    xp_ceiling: Mapped[float] = mapped_column(Float, default=0.0)
```

- [ ] **Step 4: Run → 4 passed.**

- [ ] **Step 5: Autogenerate + apply migration**

```bash
docker compose -f infra/docker-compose.yml up -d --wait
python -m alembic revision --autogenerate -m "ml tables" --rev-id 0002
python -m alembic upgrade head
python -m alembic check
```
Expected: `0002_ml_tables.py` creates the 3 tables with `uq_*` / `ix_*` / `fk_*` convention names; `alembic check` → "No new upgrade operations detected". Open the file and confirm 3 `op.create_table`.

- [ ] **Step 6: Full suite** `python -m pytest -q` → all green (new count = old + 4).

- [ ] **Step 7: Commit**

```bash
git add -A -- ':!docs'
git commit -m "feat(core): player_gw_stats / features / predictions tables + 0002 migration"
```

---

## Task 3: FPL client `event_live` + normalizer

**Files:**
- Modify: `packages/fpl_client/src/fplguru_fpl_client/client.py`
- Modify: `packages/ingest/src/fplguru_ingest/fpl.py`
- Test: `packages/fpl_client/tests/test_client.py` (append), `packages/ingest/tests/test_fpl_normalizers.py` (append)
- Create: `packages/ingest/tests/fixtures/event_live_sample.json`

- [ ] **Step 1: client test (append to `test_client.py`)**

```python
@respx.mock
async def test_event_live_returns_elements():
    respx.get(f"{BASE}/event/7/live/").mock(
        return_value=httpx.Response(200, json={"elements": [{"id": 11, "stats": {"minutes": 90}}]})
    )
    async with FplClient(BASE) as client:
        data = await client.event_live(7)
    assert data["elements"][0]["id"] == 11
```

- [ ] **Step 2: add to `client.py`** (after `fixtures`):
```python
    async def event_live(self, gameweek: int) -> dict:
        return await self._get(f"event/{gameweek}/live/")
```
Run the client tests → all pass.

- [ ] **Step 3: ingest fixture** `packages/ingest/tests/fixtures/event_live_sample.json`:
```json
{
  "elements": [
    {"id": 11, "stats": {"minutes": 90, "total_points": 9, "goals_scored": 1, "assists": 0,
      "clean_sheets": 1, "goals_conceded": 0, "bonus": 2}},
    {"id": 12, "stats": {"minutes": 0, "total_points": 0, "goals_scored": 0, "assists": 0,
      "clean_sheets": 0, "goals_conceded": 0, "bonus": 0}}
  ]
}
```

- [ ] **Step 4: ingest test (append to `test_fpl_normalizers.py`)**

```python
EVENT_LIVE = json.loads((FIX / "event_live_sample.json").read_text())


def test_normalize_event_live_maps_stats():
    rows = normalize_event_live(7, EVENT_LIVE)
    assert rows[0] == {
        "player_id": 11, "gameweek_id": 7, "minutes": 90, "total_points": 9,
        "goals": 1, "assists": 0, "clean_sheets": 1, "goals_conceded": 0, "bonus": 2,
    }
    assert rows[1]["minutes"] == 0
```
(import `normalize_event_live` in the test's import line.)

- [ ] **Step 5: add to `fpl.py`**:
```python
def normalize_event_live(gameweek_id: int, payload: dict[str, Any]) -> list[dict]:
    out = []
    for el in payload["elements"]:
        s = el["stats"]
        out.append({
            "player_id": el["id"],
            "gameweek_id": gameweek_id,
            "minutes": s["minutes"],
            "total_points": s["total_points"],
            "goals": s["goals_scored"],
            "assists": s["assists"],
            "clean_sheets": s["clean_sheets"],
            "goals_conceded": s["goals_conceded"],
            "bonus": s["bonus"],
        })
    return out
```
(`was_home` / `opponent_team_id` / `value` are filled by the worker task from `Fixture`/`Player` — not in this payload.)

- [ ] **Step 6: run both test files → green. Commit.**

```bash
git add -A -- ':!docs'
git commit -m "feat: FplClient.event_live + normalize_event_live"
```

---

## Task 4: `sync_gw_stats` worker task

**Files:**
- Modify: `services/worker/src/fplguru_worker/tasks.py`
- Test: `services/worker/tests/test_sync_gw_stats.py`

- [ ] **Step 1: failing test**

`services/worker/tests/test_sync_gw_stats.py`:
```python
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx
from sqlalchemy import func, select

from fplguru_core.models import Fixture, Gameweek, Player, PlayerGwStat, Team
from fplguru_worker.tasks import _sync_gw_stats

EVENT_LIVE = json.loads(
    (Path(__file__).parents[3] / "packages/ingest/tests/fixtures/event_live_sample.json").read_text()
)
BASE = "https://fpl.test/api"


@respx.mock
async def test_sync_gw_stats_upserts_finished_gws(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    db_session.add_all([
        Team(id=1, name="A", short_name="A"), Team(id=2, name="B", short_name="B"),
        Gameweek(id=7, name="GW7", deadline_time=datetime(2025, 10, 1, tzinfo=UTC), finished=True),
        Gameweek(id=8, name="GW8", deadline_time=datetime(2025, 10, 8, tzinfo=UTC), finished=False),
        Player(id=11, team_id=1, first_name="x", second_name="y", web_name="xy",
               position="MID", now_cost=100, status="a", selected_by_percent=1.0, total_points=9),
        Player(id=12, team_id=2, first_name="p", second_name="q", web_name="pq",
               position="DEF", now_cost=45, status="a", selected_by_percent=1.0, total_points=0),
        Fixture(id=70, gameweek_id=7, home_team_id=1, away_team_id=2,
                home_difficulty=3, away_difficulty=3, finished=True),
    ])
    await db_session.commit()
    respx.get(f"{BASE}/event/7/live/").mock(return_value=httpx.Response(200, json=EVENT_LIVE))

    await _sync_gw_stats()

    rows = (await db_session.execute(select(PlayerGwStat).order_by(PlayerGwStat.player_id))).scalars().all()
    assert [(r.player_id, r.gameweek_id, r.total_points) for r in rows] == [(11, 7, 9), (12, 7, 0)]
    assert rows[0].was_home is True and rows[0].opponent_team_id == 2   # player 11 (team 1) home vs team 2
    assert rows[1].was_home is False and rows[1].opponent_team_id == 1
    assert rows[0].value == 100
    # GW8 not finished -> not fetched
    assert not respx.routes  # only route was /event/7/live/, and it was called
```
> Adjust the final assertion form to whatever respx exposes; the intent: only finished GWs with an id are fetched, GW8 is skipped. A second `respx.get(f"{BASE}/event/8/live/")` route that is *never called* is a clean way to assert it.

- [ ] **Step 2: run → fails** (`ImportError`).

- [ ] **Step 3: implement in `tasks.py`**

```python
from fplguru_core.models import Fixture, Player, PlayerGwStat  # extend existing import
from fplguru_ingest.fpl import normalize_event_live  # extend existing import


async def _sync_gw_stats() -> None:
    started = datetime.now(UTC)
    try:
        async with get_sessionmaker()() as session, session.begin():
            finished_gw_ids = (
                await session.execute(
                    select(Gameweek.id).where(Gameweek.finished.is_(True)).order_by(Gameweek.id)
                )
            ).scalars().all()
            # player -> team, price ; fixture lookup per (gw, team)
            players = {
                p.id: p for p in (await session.execute(select(Player))).scalars().all()
            }
            fixtures = (await session.execute(
                select(Fixture).where(Fixture.gameweek_id.in_(finished_gw_ids))
            )).scalars().all()
            side = {}  # (gw_id, team_id) -> (was_home, opponent_team_id)
            for f in fixtures:
                side[(f.gameweek_id, f.home_team_id)] = (True, f.away_team_id)
                side[(f.gameweek_id, f.away_team_id)] = (False, f.home_team_id)

        client = FplClient(get_settings().fpl_api_base)
        rows: list[dict] = []
        try:
            for gw_id in finished_gw_ids:
                payload = await client.event_live(gw_id)
                for r in normalize_event_live(gw_id, payload):
                    p = players.get(r["player_id"])
                    if p is None:
                        continue
                    home_opp = side.get((gw_id, p.team_id), (False, None))
                    r["was_home"], r["opponent_team_id"] = home_opp
                    r["value"] = p.now_cost
                    rows.append(r)
        finally:
            await client.aclose()

        async with get_sessionmaker()() as session, session.begin():
            await _upsert_stats(session, rows)
            await _record(session, "fpl_gw_stats", "ok", started, f"{len(rows)} rows")
    except Exception as exc:  # noqa: BLE001
        await _log_error("fpl_gw_stats", started, exc)
        raise
```

`_upsert` keys on `id` only, so add a stats-specific upsert keyed on the `(player_id, gameweek_id)` unique constraint:
```python
async def _upsert_stats(session, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(PlayerGwStat).values(rows)
    update_cols = {
        c: stmt.excluded[c]
        for c in rows[0]
        if c not in ("player_id", "gameweek_id")
    }
    update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(
        index_elements=["player_id", "gameweek_id"], set_=update_cols
    )
    await session.execute(stmt)
```

Add the Celery wrapper + Beat entry:
```python
@celery_app.task(name="sync_gw_stats", bind=True, max_retries=3, default_retry_delay=60)
def sync_gw_stats(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_sync_gw_stats))
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc)
```
In `app.py` `beat_schedule`, add: `"sync-gw-stats": {"task": "sync_gw_stats", "schedule": 3600.0}`.

- [ ] **Step 4: run the worker tests → green.** Update `test_beat_schedule.py` to also assert `sched["sync-gw-stats"]["task"] == "sync_gw_stats"`.

- [ ] **Step 5: commit**

```bash
git add -A -- ':!docs'
git commit -m "feat(worker): sync_gw_stats — per-GW actuals from event/{gw}/live"
```

---

> **Execution order:** do **Task 6 before Task 5** — `frame.py` imports `FEATURE_NAMES` / `wmean` from `features.py`. (Task 6's Step 3 "refactor `frame.py`" then becomes a no-op / is folded into Task 5.)

## Task 5: Historical training frame

**Files:**
- Create: `packages/ml/src/fplguru_ml/frame.py`
- Create: `packages/ml/tests/fixtures/history_sample.csv`
- Test: `packages/ml/tests/test_frame.py`

- [ ] **Step 1: fixture CSV** — a hand-built history with a knowable rolling answer. `packages/ml/tests/fixtures/history_sample.csv` (columns are the vaastav `merged_gw.csv` subset the normalizer emits, plus we go straight from a DataFrame here — mirror `normalize_merged_gw` output keys):
```csv
season,player_name,position,team,gameweek,minutes,goals,assists,clean_sheet,total_points,was_home,opponent_team_id,value
24-25,Saka,MID,ARS,1,90,1,0,False,8,True,10,100
24-25,Saka,MID,ARS,2,90,0,1,False,6,False,11,100
24-25,Saka,MID,ARS,3,80,0,0,False,2,True,12,101
24-25,Saka,MID,ARS,4,90,2,0,False,13,False,13,102
24-25,Foe,DEF,LIV,1,90,0,0,True,6,True,1,45
24-25,Foe,DEF,LIV,2,90,0,0,False,2,False,1,45
24-25,Foe,DEF,LIV,3,90,0,1,True,9,True,1,45
```

- [ ] **Step 2: failing test**

`packages/ml/tests/test_frame.py`:
```python
import math
from pathlib import Path

import pandas as pd

from fplguru_ml.features import FEATURE_NAMES
from fplguru_ml.frame import build_training_frame

CSV = Path(__file__).parent / "fixtures" / "history_sample.csv"


def _rows():
    return pd.read_csv(CSV).to_dict("records")


def test_frame_has_feature_cols_and_target():
    df = build_training_frame(_rows())
    assert set(FEATURE_NAMES) <= set(df.columns)
    assert "target" in df.columns and "position" in df.columns


def test_rolling_is_leak_free_and_shifted():
    df = build_training_frame(_rows())
    saka = df[(df.player_name == "Saka")].sort_values("gameweek")
    # GW4 row: form over prior 3 appearances (GW1,2,3 points 8,6,2), weights 3,2,1 -> (24+12+2)/6
    row4 = saka[saka.gameweek == 4].iloc[0]
    assert math.isclose(row4["form_points_3"], (8 * 1 + 6 * 2 + 2 * 3) / 6, rel_tol=1e-6)
    assert row4["target"] == 13
    # GW1 & GW2 rows have < 3 priors -> dropped (NaN form)
    assert saka.gameweek.min() == 4 or saka.gameweek.min() == 3  # GW3 has 2 priors; see impl note


def test_opp_conceded_to_pos_is_present():
    df = build_training_frame(_rows())
    assert df["opp_conceded_to_pos_5"].notna().any()
```

> **Impl note on min-appearances:** require **>= 3 prior appearances** for `form_points_3` and `>= 1` for the 5-window means (they average over what's available, min 1). Rows with `< 3` priors are dropped from the *training* frame. Keep it deterministic and documented in the module docstring.

- [ ] **Step 3: implement `frame.py`**

```python
"""Historical vaastav rows -> leak-free training frame (features + target)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from fplguru_ml.features import FEATURE_NAMES

_POS = {"GK", "DEF", "MID", "FWD"}


def _wmean(vals: list[float], n: int) -> float:
    v = vals[-n:]
    if not v:
        return np.nan
    w = np.arange(1, len(v) + 1, dtype=float)
    return float(np.dot(v, w) / w.sum())


def build_training_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df = df[df["position"].isin(_POS)].copy()
    df["clean_sheet"] = df["clean_sheet"].astype(bool)
    df = df.sort_values(["season", "player_name", "gameweek"]).reset_index(drop=True)

    # --- opponent points-conceded-to-position, leak-free, per season ---
    # for each (season, opponent, position) the running mean of total_points before this GW
    df["_key"] = list(zip(df["season"], df["opponent_team_id"], df["position"]))
    concede: dict = {}
    opp_feat = []
    for r in df.itertuples():
        hist = concede.get(r._key, [])
        opp_feat.append(_wmean([float(x) for x in hist[-5:]], 5) if hist else np.nan)
        concede.setdefault(r._key, []).append(r.total_points)
    df["opp_conceded_to_pos_5"] = opp_feat

    out = []
    for (_, _), g in df.groupby(["season", "player_name"], sort=False):
        g = g.sort_values("gameweek")
        appearances = g[g["minutes"] > 0]
        pts = appearances["total_points"].tolist()
        mins = appearances["minutes"].tolist()
        gls = appearances["goals"].tolist()
        ast = appearances["assists"].tolist()
        # index within the appearance list, aligned to g rows
        seen = 0
        appset = set(appearances.index)
        for idx, r in enumerate(g.itertuples()):
            prior_pts = pts[:seen]
            prior_mins = mins[:seen]
            prior_gls = gls[:seen]
            prior_ast = ast[:seen]
            if r.Index in appset:
                seen += 1
            if len(prior_pts) < 3:
                continue
            starts = [1.0 if m >= 60 else 0.0 for m in prior_mins[-5:]]
            out.append({
                "season": r.season, "player_name": r.player_name, "position": r.position,
                "gameweek": r.gameweek,
                "form_points_3": _wmean(prior_pts, 3),
                "form_points_5": _wmean(prior_pts, 5),
                "form_minutes_3": float(np.mean(prior_mins[-3:])),
                "starts_rate_5": float(np.mean(starts)) if starts else 0.0,
                "form_goals_5": float(np.mean(prior_gls[-5:])) if prior_gls else 0.0,
                "form_assists_5": float(np.mean(prior_ast[-5:])) if prior_ast else 0.0,
                "was_home": 1.0 if bool(r.was_home) else 0.0,
                "value": float(r.value),
                "opp_conceded_to_pos_5": float(r.opp_conceded_to_pos_5)
                    if not pd.isna(r.opp_conceded_to_pos_5) else 0.0,
                "target": float(r.total_points),
            })
    frame = pd.DataFrame(out)
    # guarantee column order / presence
    for c in FEATURE_NAMES:
        if c not in frame.columns:
            frame[c] = 0.0
    return frame
```

- [ ] **Step 4: run → 3 passed. Commit.**

```bash
git add -A -- ':!docs'
git commit -m "feat(ml): leak-free historical training-frame builder"
```

---

## Task 6: `FEATURE_NAMES` + live feature row

**Files:**
- Create: `packages/ml/src/fplguru_ml/features.py`
- Test: `packages/ml/tests/test_features.py`

- [ ] **Step 1: failing test**

`packages/ml/tests/test_features.py`:
```python
from fplguru_ml.features import FEATURE_NAMES, feature_row_from_history


def test_feature_names_stable():
    assert FEATURE_NAMES == [
        "form_points_3", "form_points_5", "form_minutes_3", "starts_rate_5",
        "form_goals_5", "form_assists_5", "was_home", "value", "opp_conceded_to_pos_5",
    ]


def test_feature_row_from_history_matches_frame_semantics():
    history = [
        {"total_points": 8, "minutes": 90, "goals": 1, "assists": 0},
        {"total_points": 6, "minutes": 90, "goals": 0, "assists": 1},
        {"total_points": 2, "minutes": 80, "goals": 0, "assists": 0},
    ]
    row = feature_row_from_history(
        history,
        was_home=True,
        value=101,
        opp_conceded_to_pos_5=3.5,
    )
    assert set(row) == set(FEATURE_NAMES)
    assert abs(row["form_points_3"] - (8 * 1 + 6 * 2 + 2 * 3) / 6) < 1e-9
    assert row["was_home"] == 1.0 and row["value"] == 101.0


def test_too_few_appearances_returns_none():
    assert feature_row_from_history([{"total_points": 3, "minutes": 90, "goals": 0, "assists": 0}],
                                    was_home=False, value=50, opp_conceded_to_pos_5=0.0) is None
```

- [ ] **Step 2: implement `features.py`** — the same `_wmean` / windowing logic as `frame.py`, factored so both call it:

```python
from __future__ import annotations

import numpy as np

FEATURE_NAMES = [
    "form_points_3", "form_points_5", "form_minutes_3", "starts_rate_5",
    "form_goals_5", "form_assists_5", "was_home", "value", "opp_conceded_to_pos_5",
]


def wmean(vals, n: int) -> float:
    v = list(vals)[-n:]
    if not v:
        return float("nan")
    w = np.arange(1, len(v) + 1, dtype=float)
    return float(np.dot(v, w) / w.sum())


def feature_row_from_history(history, *, was_home: bool, value: float,
                             opp_conceded_to_pos_5: float) -> dict | None:
    """`history` = list of prior *appearances* (minutes>0), oldest-first, each with
    total_points/minutes/goals/assists. Returns None if < 3 appearances."""
    if len(history) < 3:
        return None
    pts = [float(h["total_points"]) for h in history]
    mins = [float(h["minutes"]) for h in history]
    gls = [float(h["goals"]) for h in history]
    ast = [float(h["assists"]) for h in history]
    starts = [1.0 if m >= 60 else 0.0 for m in mins[-5:]]
    return {
        "form_points_3": wmean(pts, 3),
        "form_points_5": wmean(pts, 5),
        "form_minutes_3": float(np.mean(mins[-3:])),
        "starts_rate_5": float(np.mean(starts)) if starts else 0.0,
        "form_goals_5": float(np.mean(gls[-5:])),
        "form_assists_5": float(np.mean(ast[-5:])),
        "was_home": 1.0 if was_home else 0.0,
        "value": float(value),
        "opp_conceded_to_pos_5": float(opp_conceded_to_pos_5),
    }
```

- [ ] **Step 3: refactor `frame.py`** to `from fplguru_ml.features import wmean` and delete its local `_wmean` (keep behaviour identical; re-run Task 5 tests → still green).

- [ ] **Step 4: run → green. Commit.**

```bash
git add -A -- ':!docs'
git commit -m "feat(ml): FEATURE_NAMES + shared live feature builder"
```

---

## Task 7: Closed-form ridge

**Files:**
- Create: `packages/ml/src/fplguru_ml/ridge.py`
- Test: `packages/ml/tests/test_ridge.py`

- [ ] **Step 1: failing test**

`packages/ml/tests/test_ridge.py`:
```python
import numpy as np

from fplguru_ml.ridge import RidgeModel


def test_recovers_linear_signal():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(400, 3))
    y = 2.0 * X[:, 0] - 1.0 * X[:, 1] + 0.5 + rng.normal(scale=0.01, size=400)
    m = RidgeModel.fit(X, y, feature_names=["a", "b", "c"], alpha=1e-3)
    pred = m.predict(X)
    assert np.sqrt(np.mean((pred - y) ** 2)) < 0.1
    assert abs(m.coef_[0] - 2.0) < 0.1 and abs(m.coef_[2]) < 0.1


def test_json_round_trip():
    X = np.random.default_rng(1).normal(size=(50, 2))
    y = X @ np.array([1.0, -2.0]) + 3.0
    m = RidgeModel.fit(X, y, feature_names=["x", "y"], alpha=0.1)
    m2 = RidgeModel.from_json(m.to_json())
    assert np.allclose(m.predict(X), m2.predict(X))
    assert m2.feature_names == ["x", "y"]


def test_predict_checks_feature_count():
    m = RidgeModel.fit(np.zeros((3, 2)), np.zeros(3), feature_names=["a", "b"], alpha=1.0)
    try:
        m.predict(np.zeros((3, 3)))
    except ValueError:
        return
    raise AssertionError("expected ValueError on wrong feature count")
```

- [ ] **Step 2: implement `ridge.py`**

```python
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np


@dataclass
class RidgeModel:
    feature_names: list[str]
    mean_: np.ndarray      # (d,) standardization mean
    std_: np.ndarray       # (d,) standardization std (zeros -> 1)
    coef_: np.ndarray      # (d,) on standardized X
    intercept_: float
    alpha: float

    @classmethod
    def fit(cls, X, y, *, feature_names: list[str], alpha: float) -> "RidgeModel":
        X = np.asarray(X, float)
        y = np.asarray(y, float)
        mean = X.mean(axis=0)
        std = X.std(axis=0)
        std[std == 0] = 1.0
        Xs = (X - mean) / std
        d = Xs.shape[1]
        A = Xs.T @ Xs + alpha * np.eye(d)
        b = Xs.T @ (y - y.mean())
        coef = np.linalg.solve(A, b)
        return cls(list(feature_names), mean, std, coef, float(y.mean()), float(alpha))

    def predict(self, X) -> np.ndarray:
        X = np.asarray(X, float)
        if X.shape[1] != len(self.feature_names):
            raise ValueError(f"expected {len(self.feature_names)} features, got {X.shape[1]}")
        Xs = (X - self.mean_) / self.std_
        return Xs @ self.coef_ + self.intercept_

    def to_json(self) -> str:
        return json.dumps({
            "feature_names": self.feature_names,
            "mean": self.mean_.tolist(), "std": self.std_.tolist(),
            "coef": self.coef_.tolist(), "intercept": self.intercept_, "alpha": self.alpha,
        })

    @classmethod
    def from_json(cls, s: str) -> "RidgeModel":
        d = json.loads(s)
        return cls(d["feature_names"], np.array(d["mean"]), np.array(d["std"]),
                   np.array(d["coef"]), float(d["intercept"]), float(d["alpha"]))
```

- [ ] **Step 3: run → 3 passed. Commit.**

```bash
git add -A -- ':!docs'
git commit -m "feat(ml): closed-form ridge model with JSON persistence"
```

---

## Task 8: `BasicXP` — per-position bundle + fallback

**Files:**
- Create: `packages/ml/src/fplguru_ml/model_basic.py`
- Test: `packages/ml/tests/test_model_basic.py`

- [ ] **Step 1: failing test**

`packages/ml/tests/test_model_basic.py`:
```python
from pathlib import Path

import pandas as pd

from fplguru_ml.frame import build_training_frame
from fplguru_ml.model_basic import BasicXP, train_basic

CSV = Path(__file__).parents[1] / "tests" / "fixtures" / "history_sample.csv"  # reuse Task 5 fixture


def _frame():
    return build_training_frame(pd.read_csv(CSV).to_dict("records"))


def test_trains_a_model_per_present_position():
    m = train_basic(_frame(), alpha=1.0)
    assert set(m.positions()) <= {"GK", "DEF", "MID", "FWD"}
    assert "MID" in m.positions()  # Saka rows survive the >=3-prior filter


def test_predict_rows_returns_one_per_row():
    m = train_basic(_frame(), alpha=1.0)
    feats = [{k: 0.0 for k in __import__("fplguru_ml.features", fromlist=["FEATURE_NAMES"]).FEATURE_NAMES}]
    out = m.predict_rows("MID", feats)
    assert len(out) == 1 and isinstance(out[0], float)


def test_unknown_position_uses_global_mean(tmp_path):
    m = train_basic(_frame(), alpha=1.0)
    # GK not in the sample -> falls back to the global training-target mean
    val = m.predict_rows("GK", [{k: 0.0 for k in m.feature_names}])[0]
    assert isinstance(val, float)


def test_save_load_round_trip(tmp_path):
    m = train_basic(_frame(), alpha=1.0)
    m.save(tmp_path)
    m2 = BasicXP.load(tmp_path)
    r = [{k: 1.0 for k in m.feature_names}]
    assert abs(m.predict_rows("MID", r)[0] - m2.predict_rows("MID", r)[0]) < 1e-9
    assert m2.version == m.version
```

- [ ] **Step 2: implement `model_basic.py`**

```python
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fplguru_ml.features import FEATURE_NAMES
from fplguru_ml.ridge import RidgeModel

VERSION = "basic-v1"


class BasicXP:
    def __init__(self, models: dict[str, RidgeModel], global_mean: float,
                 version: str = VERSION) -> None:
        self._models = models
        self._global_mean = float(global_mean)
        self.version = version
        self.feature_names = list(FEATURE_NAMES)

    def positions(self) -> list[str]:
        return sorted(self._models)

    def predict_rows(self, position: str, rows: list[dict]) -> list[float]:
        X = np.array([[float(r[k]) for k in self.feature_names] for r in rows], float)
        model = self._models.get(position)
        if model is None or len(rows) == 0:
            return [self._global_mean] * len(rows)
        return [float(v) for v in model.predict(X)]

    def save(self, directory) -> None:
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps(
            {"version": self.version, "global_mean": self._global_mean,
             "feature_names": self.feature_names, "positions": self.positions()}))
        for pos, model in self._models.items():
            (d / f"{pos}.json").write_text(model.to_json())

    @classmethod
    def load(cls, directory) -> "BasicXP":
        d = Path(directory)
        meta = json.loads((d / "meta.json").read_text())
        models = {pos: RidgeModel.from_json((d / f"{pos}.json").read_text())
                  for pos in meta["positions"]}
        return cls(models, meta["global_mean"], meta["version"])


def train_basic(frame: pd.DataFrame, *, alpha: float = 1.0) -> BasicXP:
    if frame.empty:
        return BasicXP({}, 0.0)
    models: dict[str, RidgeModel] = {}
    for pos, g in frame.groupby("position"):
        if len(g) < len(FEATURE_NAMES) + 1:   # not enough rows to fit
            continue
        X = g[FEATURE_NAMES].to_numpy(float)
        y = g["target"].to_numpy(float)
        models[pos] = RidgeModel.fit(X, y, feature_names=FEATURE_NAMES, alpha=alpha)
    return BasicXP(models, float(frame["target"].mean()))
```

- [ ] **Step 3: run → passed. Commit.**

```bash
git add -A -- ':!docs'
git commit -m "feat(ml): BasicXP per-position bundle with position-mean fallback"
```

---

## Task 9: Walk-forward backtest

**Files:**
- Create: `packages/ml/src/fplguru_ml/backtest.py`
- Test: `packages/ml/tests/test_backtest.py`

- [ ] **Step 1: failing test**

`packages/ml/tests/test_backtest.py`:
```python
import numpy as np
import pandas as pd

from fplguru_ml.features import FEATURE_NAMES
from fplguru_ml.backtest import walk_forward


def _synthetic(n_gw=12, players_per_pos=15):
    rng = np.random.default_rng(3)
    rows = []
    for pos, w in (("MID", 4.0), ("DEF", 2.5)):
        for p in range(players_per_pos):
            for gw in range(1, n_gw + 1):
                feats = {k: float(rng.normal()) for k in FEATURE_NAMES}
                target = w * feats["form_points_5"] + 0.3 * feats["was_home"] + rng.normal(scale=0.5)
                rows.append({"season": "s", "player_name": f"{pos}{p}", "position": pos,
                             "gameweek": gw, "target": target, **feats})
    return pd.DataFrame(rows)


def test_walk_forward_beats_naive_mean():
    frame = _synthetic()
    res = walk_forward(frame, alpha=1.0, min_train_gw=4)
    m = res.metrics_by_position()
    assert set(m) == {"MID", "DEF"}
    # model RMSE should beat "predict the training mean"
    assert m["MID"]["rmse"] < m["MID"]["baseline_rmse"]
    assert m["MID"]["n"] > 0


def test_no_leakage_each_fold_trains_on_past_only():
    frame = _synthetic()
    res = walk_forward(frame, alpha=1.0, min_train_gw=4)
    assert res.folds[0].train_max_gw < res.folds[0].test_gw
```

- [ ] **Step 2: implement `backtest.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from fplguru_ml.features import FEATURE_NAMES
from fplguru_ml.model_basic import train_basic


@dataclass
class Fold:
    test_gw: int
    train_max_gw: int
    rows: pd.DataFrame  # test rows with columns: position, target, pred, baseline


@dataclass
class BacktestResult:
    folds: list[Fold] = field(default_factory=list)

    def _all(self) -> pd.DataFrame:
        return pd.concat([f.rows for f in self.folds], ignore_index=True) if self.folds else pd.DataFrame()

    def metrics_by_position(self) -> dict[str, dict]:
        df = self._all()
        out: dict[str, dict] = {}
        for pos, g in df.groupby("position"):
            err = g["pred"] - g["target"]
            berr = g["baseline"] - g["target"]
            out[pos] = {
                "n": int(len(g)),
                "mae": float(err.abs().mean()),
                "rmse": float(np.sqrt((err ** 2).mean())),
                "baseline_rmse": float(np.sqrt((berr ** 2).mean())),
            }
        return out


def walk_forward(frame: pd.DataFrame, *, alpha: float = 1.0, min_train_gw: int = 5) -> BacktestResult:
    res = BacktestResult()
    gws = sorted(frame["gameweek"].unique())
    for test_gw in gws:
        train = frame[frame["gameweek"] < test_gw]
        if train.empty or train["gameweek"].nunique() < min_train_gw:
            continue
        test = frame[frame["gameweek"] == test_gw]
        if test.empty:
            continue
        model = train_basic(train, alpha=alpha)
        pos_mean = train.groupby("position")["target"].mean().to_dict()
        parts = []
        for pos, g in test.groupby("position"):
            preds = model.predict_rows(pos, g[FEATURE_NAMES].to_dict("records"))
            parts.append(pd.DataFrame({
                "position": pos, "target": g["target"].to_numpy(float),
                "pred": preds, "baseline": pos_mean.get(pos, train["target"].mean()),
            }))
        res.folds.append(Fold(int(test_gw), int(train["gameweek"].max()),
                              pd.concat(parts, ignore_index=True)))
    return res
```

- [ ] **Step 3: run → 2 passed. Commit.**

```bash
git add -A -- ':!docs'
git commit -m "feat(ml): walk-forward backtest with per-position MAE/RMSE vs baseline"
```

---

## Task 10: Multi-GW rollout

**Files:**
- Create: `packages/ml/src/fplguru_ml/rollout.py`
- Test: `packages/ml/tests/test_rollout.py`

- [ ] **Step 1: failing test**

`packages/ml/tests/test_rollout.py`:
```python
from fplguru_ml.features import FEATURE_NAMES
from fplguru_ml.model_basic import train_basic
from fplguru_ml.rollout import project_horizon


class _StubModel:
    version = "stub"
    feature_names = FEATURE_NAMES

    def predict_rows(self, position, rows):
        return [3.0 for _ in rows]


def test_projects_each_gw_and_cumulates():
    per_gw = [{k: 0.0 for k in FEATURE_NAMES} for _ in range(5)]
    hp = project_horizon("MID", per_gw, _StubModel())
    assert [round(p.xp, 3) for p in hp.per_gw] == [3.0, 3.0, 3.0, 3.0, 3.0]
    assert round(hp.cumulative, 3) == 15.0
    assert hp.per_gw[0].horizon_gw == 1 and hp.per_gw[4].horizon_gw == 5


def test_confidence_band_widens_with_horizon():
    per_gw = [{k: 0.0 for k in FEATURE_NAMES} for _ in range(5)]
    hp = project_horizon("MID", per_gw, _StubModel())
    spreads = [p.ceiling - p.floor for p in hp.per_gw]
    assert spreads == sorted(spreads) and spreads[4] > spreads[0]
```

- [ ] **Step 2: implement `rollout.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

_BASE_SPREAD = 4.0     # +/- points at horizon 1
_GROWTH = 0.35         # widen per extra GW


@dataclass
class GwPrediction:
    horizon_gw: int
    xp: float
    floor: float
    ceiling: float


@dataclass
class HorizonPrediction:
    position: str
    per_gw: list[GwPrediction]

    @property
    def cumulative(self) -> float:
        return float(sum(p.xp for p in self.per_gw))


def project_horizon(position: str, per_gw_feature_rows: list[dict], model) -> HorizonPrediction:
    xps = model.predict_rows(position, per_gw_feature_rows)
    out = []
    for i, xp in enumerate(xps, start=1):
        half = _BASE_SPREAD * (1.0 + _GROWTH * (i - 1)) / 2.0
        out.append(GwPrediction(i, float(xp), float(xp - half), float(xp + half)))
    return HorizonPrediction(position, out)
```

> Basic tier keeps rollout simple: each future GW is predicted independently with the player's **current** form held constant (the caller supplies one feature row per future GW, differing only by `was_home` / `opp_conceded_to_pos_5` for that GW's fixture). Compounding rotation/fixture-swing modelling is Advanced-tier (P2b).

- [ ] **Step 3: run → 2 passed. Commit.**

```bash
git add -A -- ':!docs'
git commit -m "feat(ml): multi-GW horizon rollout with widening confidence band"
```

---

## Task 11: Training + backtest CLIs

**Files:**
- Create: `scripts/train_xp.py`, `scripts/backtest_xp.py`
- Create: `packages/ml/artifacts/basic/.gitkeep`
- Test: `packages/ml/tests/test_cli.py`

- [ ] **Step 1: failing test**

`packages/ml/tests/test_cli.py`:
```python
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SAMPLE = REPO / "packages/ml/tests/fixtures/history_sample.csv"


def test_train_cli_writes_artifacts(tmp_path):
    out = tmp_path / "model"
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts/train_xp.py"),
         "--csv", str(SAMPLE), "--out", str(out)],
        capture_output=True, text=True, cwd=REPO,
    )
    assert r.returncode == 0, r.stderr
    assert (out / "meta.json").exists()
    from fplguru_ml.model_basic import BasicXP
    assert "MID" in BasicXP.load(out).positions()


def test_backtest_cli_writes_report(tmp_path):
    rep = tmp_path / "bt.md"
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts/backtest_xp.py"),
         "--csv", str(SAMPLE), "--out", str(rep), "--min-train-gw", "1"],
        capture_output=True, text=True, cwd=REPO,
    )
    assert r.returncode == 0, r.stderr
    body = rep.read_text()
    assert "| position |" in body.lower() and "rmse" in body.lower()
```

- [ ] **Step 2: `scripts/train_xp.py`**

```python
"""Train the Basic xP model from vaastav merged_gw CSV(s).

  python scripts/train_xp.py --csv data/historical/2023-24_merged_gw.csv \\
      data/historical/2024-25_merged_gw.csv --out packages/ml/artifacts/basic
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from fplguru_ingest.historical import normalize_merged_gw
from fplguru_ml.frame import build_training_frame
from fplguru_ml.model_basic import train_basic


def _rows(paths: list[str]) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        season = Path(p).stem.split("_")[0]
        try:
            rows += normalize_merged_gw(p, season=season)
        except Exception:  # noqa: BLE001 - a raw sample CSV already in normalized shape
            rows += pd.read_csv(p).assign(season=season).to_dict("records")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", nargs="+", required=True)
    ap.add_argument("--out", default="packages/ml/artifacts/basic")
    ap.add_argument("--alpha", type=float, default=1.0)
    args = ap.parse_args()
    frame = build_training_frame(_rows(args.csv))
    model = train_basic(frame, alpha=args.alpha)
    model.save(args.out)
    print(f"trained {model.version}: positions={model.positions()} rows={len(frame)} -> {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: `scripts/backtest_xp.py`**

```python
"""Walk-forward backtest of the Basic xP model; writes a Markdown report."""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd

from fplguru_ingest.historical import normalize_merged_gw
from fplguru_ml.backtest import walk_forward
from fplguru_ml.frame import build_training_frame


def _rows(paths):
    rows = []
    for p in paths:
        season = Path(p).stem.split("_")[0]
        try:
            rows += normalize_merged_gw(p, season=season)
        except Exception:  # noqa: BLE001
            rows += pd.read_csv(p).assign(season=season).to_dict("records")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", nargs="+", required=True)
    ap.add_argument("--out", default=f"docs/xp-backtest/{dt.date.today():%Y-%m-%d}.md")
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--min-train-gw", type=int, default=5)
    args = ap.parse_args()

    frame = build_training_frame(_rows(args.csv))
    res = walk_forward(frame, alpha=args.alpha, min_train_gw=args.min_train_gw)
    m = res.metrics_by_position()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Basic xP backtest — {dt.date.today():%Y-%m-%d}",
        "",
        f"- rows: {len(frame)}  · folds: {len(res.folds)}  · alpha: {args.alpha}",
        "",
        "| position | n | MAE | RMSE | baseline RMSE | beats baseline |",
        "|---|---:|---:|---:|---:|:--:|",
    ]
    for pos in sorted(m):
        r = m[pos]
        lines.append(
            f"| {pos} | {r['n']} | {r['mae']:.3f} | {r['rmse']:.3f} | "
            f"{r['baseline_rmse']:.3f} | {'✅' if r['rmse'] < r['baseline_rmse'] else '❌'} |"
        )
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: run the CLI tests → 2 passed.** Then, if `data/historical/` has real CSVs, run for real and commit the resulting `docs/xp-backtest/<date>.md` + `packages/ml/artifacts/basic/*.json` (the artifact JSONs are small — commit them).

- [ ] **Step 5: commit**

```bash
git add -A -- ':!docs'
git commit -m "feat(ml): train_xp / backtest_xp CLIs"
# then, separately, the generated artifacts + report:
git add packages/ml/artifacts docs/xp-backtest
git commit -m "chore(ml): committed basic-v1 artifacts + first backtest report"
```

---

## Task 12: `compute_xp` worker task

**Files:**
- Modify: `services/worker/src/fplguru_worker/tasks.py`, `services/worker/src/fplguru_worker/app.py`
- Create: `services/worker/src/fplguru_worker/xp.py` (the feature-assembly + predict logic, kept out of `tasks.py`)
- Test: `services/worker/tests/test_compute_xp.py`

- [ ] **Step 1: failing test**

`services/worker/tests/test_compute_xp.py`:
```python
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from fplguru_core.models import (Fixture, Gameweek, Player, PlayerGwPrediction, PlayerGwStat, Team)
from fplguru_worker.xp import compute_and_store_xp


@pytest.fixture
def _seed_ready(db_session):
    async def _go():
        db_session.add_all([
            Team(id=1, name="A", short_name="A"), Team(id=2, name="B", short_name="B"),
            Gameweek(id=1, name="GW1", deadline_time=datetime(2025, 8, 1, tzinfo=UTC), finished=True),
            Gameweek(id=2, name="GW2", deadline_time=datetime(2025, 8, 8, tzinfo=UTC), finished=True),
            Gameweek(id=3, name="GW3", deadline_time=datetime(2025, 8, 15, tzinfo=UTC), finished=True),
            Gameweek(id=4, name="GW4", deadline_time=datetime(2025, 8, 22, tzinfo=UTC),
                     is_next=True, finished=False),
            Player(id=11, team_id=1, first_name="x", second_name="y", web_name="xy",
                   position="MID", now_cost=100, status="a", selected_by_percent=1.0, total_points=20),
            Fixture(id=104, gameweek_id=4, home_team_id=1, away_team_id=2,
                    home_difficulty=3, away_difficulty=3, finished=False),
        ])
        for gw, pts in ((1, 8), (2, 6), (3, 2)):
            db_session.add(PlayerGwStat(player_id=11, gameweek_id=gw, minutes=90,
                                        total_points=pts, goals=0, assists=0, clean_sheets=0,
                                        goals_conceded=0, bonus=0, was_home=True,
                                        opponent_team_id=2, value=100))
        await db_session.commit()
    return _go


async def test_compute_xp_writes_predictions_for_horizon(_seed_ready, tmp_path, monkeypatch):
    await _seed_ready()
    # tiny model: predict a constant so the test is deterministic
    from fplguru_ml.model_basic import BasicXP
    from fplguru_ml.ridge import RidgeModel
    import numpy as np
    from fplguru_ml.features import FEATURE_NAMES
    rm = RidgeModel.fit(np.ones((20, len(FEATURE_NAMES))), np.full(20, 5.0),
                        feature_names=FEATURE_NAMES, alpha=1.0)
    BasicXP({"MID": rm}, global_mean=2.0).save(tmp_path)
    monkeypatch.setenv("FPLGURU_XP_ARTIFACT_DIR", str(tmp_path))

    await compute_and_store_xp(horizon=1)

    rows = (await select(PlayerGwPrediction).__await_via_session__)  # see impl: use db_session
```
> Rework the last lines to query via the test's `db_session` (the `_seed_ready` closure already has it). The assertion: exactly one `PlayerGwPrediction` row for `player_id=11`, `gameweek_id=4`, `horizon_gw=1`, `model_version="basic-v1"`, `xp` finite. Second call → still one row (idempotent upsert on `(player_id, gameweek_id, model_version)`).

- [ ] **Step 2: implement `services/worker/src/fplguru_worker/xp.py`**

Responsibilities:
1. Load `BasicXP` from `settings`-configurable dir (`FPLGURU_XP_ARTIFACT_DIR`, default `packages/ml/artifacts/basic`).
2. Query the next `horizon` unfinished gameweeks (ordered by `deadline_time`).
3. For each `Player` with `status == "a"`: pull their last ≤5 `PlayerGwStat` rows (minutes > 0), build the appearance history list; for each target GW find the player's `Fixture` (via team), compute `was_home` + `opp_conceded_to_pos_5` (rolling from `PlayerGwStat` joined to opponent + position — reuse the same windowing as `frame.py`); `feature_row_from_history(...)`; if `None` (too few appearances) skip or use fallback.
4. `project_horizon(pos, rows, model)` → per-GW `GwPrediction`.
5. Upsert `PlayerGwPrediction` rows keyed on `(player_id, gameweek_id, model_version)` — `horizon_gw` = index, `xp`/`xp_floor`/`xp_ceiling` from the projection. (Component fields `x_*` stay 0.0 for Basic v1 — the linear model has no component breakdown; note this in the module docstring and fill them in Advanced-tier.)
6. Write a `DataSyncLog("xp_compute", "ok", ...)` row.

Add a settings field `xp_artifact_dir: str = "packages/ml/artifacts/basic"` to `fplguru_core.settings.Settings`.

- [ ] **Step 3: `tasks.py` + `app.py`**

```python
# tasks.py
from fplguru_worker.xp import compute_and_store_xp

@celery_app.task(name="compute_xp", bind=True, max_retries=3, default_retry_delay=120)
def compute_xp(self) -> None:
    try:
        asyncio.run(_run_and_dispose(lambda: compute_and_store_xp(horizon=5)))
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc)
```
`app.py` beat: `"compute-xp": {"task": "compute_xp", "schedule": 3600.0}`. Update `test_beat_schedule.py`.

- [ ] **Step 4: run worker tests → green; full `python -m pytest -q` → green. Commit.**

```bash
git add -A -- ':!docs'
git commit -m "feat(worker): compute_xp — assemble features from DB, predict, upsert predictions"
```

---

## Task 13: xP API endpoints

**Files:**
- Modify: `services/api/src/fplguru_api/main.py`
- Test: `services/api/tests/test_xp_api.py`

- [ ] **Step 1: failing test**

`services/api/tests/test_xp_api.py`:
```python
from datetime import UTC, datetime

from fplguru_core.models import Gameweek, Player, PlayerGwPrediction, Team


async def _seed(db_session):
    db_session.add_all([
        Team(id=1, name="A", short_name="A"),
        Gameweek(id=4, name="GW4", deadline_time=datetime(2025, 8, 22, tzinfo=UTC), is_next=True),
        Gameweek(id=5, name="GW5", deadline_time=datetime(2025, 8, 29, tzinfo=UTC)),
        Player(id=11, team_id=1, first_name="x", second_name="y", web_name="Saka",
               position="MID", now_cost=100, status="a", selected_by_percent=1.0, total_points=0),
    ])
    for gw, h, xp in ((4, 1, 5.5), (5, 2, 4.0)):
        db_session.add(PlayerGwPrediction(player_id=11, gameweek_id=gw, horizon_gw=h,
                                          model_version="basic-v1", xp=xp,
                                          xp_floor=xp - 2, xp_ceiling=xp + 2))
    await db_session.commit()


async def test_player_xp_breakdown(client, db_session):
    await _seed(db_session)
    r = await client.get("/players/11/xp?horizon=5")
    body = r.json()
    assert body["player_id"] == 11 and body["web_name"] == "Saka"
    assert [g["horizon_gw"] for g in body["per_gw"]] == [1, 2]
    assert abs(body["xp_total"] - 9.5) < 1e-6


async def test_xp_list_sorted_desc(client, db_session):
    await _seed(db_session)
    db_session.add(Player(id=12, team_id=1, first_name="a", second_name="b", web_name="Low",
                          position="DEF", now_cost=40, status="a", selected_by_percent=1.0,
                          total_points=0))
    db_session.add(PlayerGwPrediction(player_id=12, gameweek_id=4, horizon_gw=1,
                                      model_version="basic-v1", xp=1.0, xp_floor=0, xp_ceiling=2))
    await db_session.commit()
    r = await client.get("/xp?horizon=5")
    rows = r.json()
    assert [x["player_id"] for x in rows] == [11, 12]           # 9.5 then 1.0
    assert rows[0]["xp_total"] == 9.5


async def test_player_xp_404_when_no_predictions(client, db_session):
    await _seed(db_session)
    r = await client.get("/players/999/xp")
    assert r.status_code == 404
```

- [ ] **Step 2: implement in `main.py`**

```python
from fastapi import HTTPException, Query
from fplguru_core.models import Player, PlayerGwPrediction   # extend imports

_MODEL_VERSION = "basic-v1"


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
    player = (await db.execute(select(Player).where(Player.id == player_id))).scalar_one_or_none()
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
```

- [ ] **Step 3: run api tests → green; full suite → green. Commit.**

```bash
git add -A -- ':!docs'
git commit -m "feat(api): GET /xp and GET /players/{id}/xp"
```

---

## Task 14: Beat wiring check, CI, README, docs

**Files:**
- Modify: `services/worker/tests/test_beat_schedule.py`, `README.md`, `docs/RESUME-foundation.md`, `docs/plans/2026-08-27-fplguru-master-build-plan.md`
- Create: `docs/xp-backtest/.gitkeep` (if not already present from Task 11)

- [ ] **Step 1: `test_beat_schedule.py`** — assert all four tasks now present: `sync_bootstrap`, `sync_fixtures`, `sync_gw_stats`, `compute_xp`.

- [ ] **Step 2: CI** — no workflow change needed (pytest picks up `packages/ml/tests` via `testpaths`). Confirm `.github/workflows/ci.yml` still just runs `python -m pytest -q`. If the `subprocess` CLI tests (Task 11) are slow, mark them `@pytest.mark.slow` and leave them in the default run anyway (they use the 7-row fixture — fast).

- [ ] **Step 3: `README.md`** — add an "xP model" section:
```markdown
## xP model (Basic)

```bash
# one-time: pull historical data
python scripts/fetch_historical.py 2022-23 2023-24 2024-25

# train + backtest
python scripts/train_xp.py --csv data/historical/*.csv --out packages/ml/artifacts/basic
python scripts/backtest_xp.py --csv data/historical/*.csv     # writes docs/xp-backtest/<date>.md

# serve: the worker's compute_xp task fills player_gw_predictions hourly;
# GET /xp?horizon=5  and  GET /players/{id}/xp
```
```

- [ ] **Step 4: master plan** — mark sub-plan **P1c** ✅ in the §3 table; note "Basic xP serving `player_gw_predictions`; backtest report at `docs/xp-backtest/`".

- [ ] **Step 5: full `python -m pytest -q` + (if ruff available) `python -m ruff check .` → green. Commit.**

```bash
git add -A -- ':!docs'
git commit -m "chore: beat wiring for compute_xp; docs for the xP model"
git add docs
git commit -m "docs: P1c complete — Basic xP engine"
```

---

## Self-Review

**1. Spec coverage (master plan §5.2 Basic tier / P1c):**
- Per-player xP over 1–5 GW horizon, default 5 → Tasks 10, 12, 13 ✓
- Component breakdown → `PlayerGwPrediction.x_*` columns exist (Task 2); **left 0.0 for Basic v1** — linear model has no component split. Explicitly deferred to Advanced (P2b). Documented in `xp.py`.
- Confidence/variance band → widening floor/ceiling (Task 10) ✓ (crude for Basic; quantile regression is Advanced)
- Feature set §5.3 subset available FPL-only + leak-safe → Tasks 5, 6 ✓ (rolling form, minutes, home/away, value, opp-conceded-to-position). Opponent xG / set-piece role / injury-doubt% are Advanced/other sub-plans.
- Two model tiers → this builds the **Basic** tier; ridge per position group (§5.4 "one model per position group") ✓
- Multi-GW rollout §5.5 → Task 10; Basic = independent per-GW (compounding is Advanced) ✓
- Backtest MAE/RMSE per position vs historical, report checked into `docs/` → Tasks 9, 11 ✓
- Serving layer, recompute on cadence → Task 12 + Beat ✓
- Data source: official FPL API + vaastav historical → Tasks 3, 4, 11 ✓

**2. Placeholder scan:** Two tasks (10, 12) have a `> Rework the last lines…` note on a test snippet where the exact query form depends on the session fixture — the intent and assertions are fully specified, only the 2-3 lines of `db_session.execute(select(...))` plumbing are left to match the surrounding file's style. Everything else is complete code.

**3. Type/name consistency:**
- `FEATURE_NAMES` (list, fixed order) defined once in `features.py`; `frame.py`, `model_basic.py`, `backtest.py`, tests all import it ✓
- `wmean(vals, n)` shared by `features.py` and `frame.py` (Task 6 Step 3 refactor) ✓
- `RidgeModel.fit(X, y, *, feature_names, alpha)` / `.predict(X)` / `.to_json()` / `.from_json(s)` — same signature in Tasks 7, 8, 9, 12 ✓
- `BasicXP.predict_rows(position, rows: list[dict]) -> list[float]`, `.positions()`, `.save(dir)`, `.load(dir)`, `.version`, `.feature_names` — consistent across Tasks 8–13 ✓
- `project_horizon(position, per_gw_feature_rows, model) -> HorizonPrediction` with `.per_gw[i].horizon_gw/xp/floor/ceiling` and `.cumulative` — Tasks 10, 12 ✓
- `PlayerGwPrediction` unique key `(player_id, gameweek_id, model_version)` — upsert in Task 12, read in Task 13 ✓
- `model_version` string `"basic-v1"` == `BasicXP.VERSION` == API `_MODEL_VERSION` ✓
- `PlayerGwStat` unique key `(player_id, gameweek_id)` — `_upsert_stats` (Task 4) ✓
- `DataSyncLog.source` new values `"fpl_gw_stats"`, `"xp_compute"` — consistent with the `/status` loop? **`/status` only reports `fpl_bootstrap`/`fpl_fixtures`** — Task 14 should extend that loop (or make `/status` enumerate distinct sources from the table). **Added to Task 14 Step 3.** (edit: fold into Task 13 `main.py` change — enumerate `select(distinct(DataSyncLog.source))` instead of the hardcoded tuple.)

---

## Execution Handoff

Plan saved to `docs/plans/2026-08-27-p1c-basic-xp-engine.md`. Branch: `feature/basic-xp` (off `main`).

**Subagent-Driven (recommended)** — fresh subagent per task, spec + code review each, same as Foundation. Tasks 5–10 (the ML core) warrant full two-stage review; Tasks 1, 3, 14 are mechanical (spec-check only).

Prerequisite before Task 11's "for real" run and Task 12's live use: `python scripts/fetch_historical.py 2022-23 2023-24 2024-25` (needs network; writes gitignored `data/historical/`).
