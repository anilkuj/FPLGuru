# P1b — Live Scores & GW Live Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development — one implementer subagent per task, then a spec-compliance review and a code-quality review, fix loop, commit, next task. Steps use `- [ ]` checkboxes.

**Goal:** During matches, show every featured player's live FPL points plus a BPS-based bonus projection, updating a "GW Live" web page in near-real-time over Server-Sent Events.

**Architecture:** A worker task (`poll_live`) polls `fixtures` + `event/{gw}/live` on a fast Beat schedule *only while a match is in play*, computes provisional 3/2/1 bonus per fixture from BPS, and upserts one row per (player, current-GW) into a new `player_gw_live` table. The read-only API exposes a JSON snapshot (`GET /gameweeks/current/live`) and an SSE stream (`GET /gameweeks/current/live/stream`) that re-reads that table every few seconds and pushes a new event whenever `updated_at` advances. The Next.js `/live` page renders a fixtures strip + a sortable player board, subscribes to the SSE stream, and falls back to polling if the stream errors.

**Tech Stack:** SQLAlchemy 2.0 async + Alembic (`0004`), Celery + Beat, FastAPI `StreamingResponse` (hand-rolled SSE, no new dependency), a new pure package `fplguru-live`, Next.js 16 App Router + `EventSource`, Vitest 4.

---

## Project context (read once — every task assumes this)

- **Monorepo** `D:\AntiGravity\FPLGuru`. Work on branch **`feature/p1b-live-scores`** off `main`.
- **Toolchain (Smart App Control is ON):** `venv` + `pip`, never `uv`. Every tool is `python -m <tool>` (`python -m pytest`, `python -m ruff`, `python -m alembic`). `ruff` works locally. Activate the venv first: `source .venv/Scripts/activate` (Git Bash) — or call `.venv/Scripts/python.exe` directly. Chain shell commands (`cd` in a compound command can prompt).
- **Docker must be up:** `docker compose -f infra/docker-compose.yml up -d --wait` (Postgres + Redis; project name `fplguru`).
- **Editable installs:** each package/service is listed in `requirements-dev.txt` as `-e ./packages/<x>`. A **new** package must be added there, then `python -m pip install -r requirements-dev.txt`.
- **Models have NO `relationship()`.** In test seeds, insert FK-parent rows and `await session.commit()` *before* inserting children (commit waves). Use real `datetime(..., tzinfo=UTC)` objects for `DateTime(timezone=True)` columns — asyncpg rejects strings.
- **`Base.metadata` has a `naming_convention`;** FK constraint token is `referred_table_name`. Natural-key PKs (`Team/Gameweek/Player/Fixture.id`) are `autoincrement=False`. Surrogate PKs are `BigInteger` `autoincrement=True`. `_TimestampMixin` adds only `updated_at` (server_default `now()`).
- **Migrations:** `alembic/versions/000N_*.py`. `revision`/`down_revision` are plain zero-padded strings (`'0001'`…`'0003'`). CI runs `python -m alembic check` as a model↔migration drift guard — it must stay clean. `alembic/*` is ruff-exempt for `E402,E501,I001,UP035,UP007`.
- **Every migration task also updates** `packages/core/tests/test_models.py::test_expected_tables_registered` (an exact-set assertion) to add the new table name(s).
- **Worker pattern:** each Celery task body is `asyncio.run(_run_and_dispose(_the_async_fn))`; `_run_and_dispose` disposes the process-cached engine + `reset_state()` afterwards (fixes prefork loop reuse). Async helpers open `async with get_sessionmaker()() as session, session.begin():` blocks. Errors go through `_log_error(source, started, exc)` on a fresh session, then `raise`. `_upsert(session, model, rows)` upserts on the `id` PK; `_upsert_stats`-style helpers upsert on a natural unique key. Worker runs `-P prefork`/`-P solo` only.
- **API:** `services/api/src/fplguru_api/main.py`. `get_db` yields a read-only `AsyncSession`; `lifespan` disposes the engine. Current imports include `from fastapi import Depends, FastAPI, HTTPException, Query` and `from sqlalchemy import desc, distinct, func, select, text`. Tests: `services/api/tests/conftest.py` provides `client` (ASGI, `get_db` overridden onto the test DB); root `conftest.py` provides `db_session` and an autouse `_point_app_at_test_db`.
- **Web:** `apps/web`, Next 16, Tailwind v4, Vitest 4 (`vitest.config.mts`). `NEXT_PUBLIC_API_BASE` default `http://localhost:8000`. `src/lib/api.ts` has a private `async function asJson<T>(res)` helper and existing `getEntry`. `src/lib/entry.ts` exposes `getStoredEntryId()` (localStorage key `fplguru.entryId`). Pages are server components that render a `"use client"` child (see `src/app/squad/`). Run web checks from `apps/web`: `./node_modules/.bin/vitest run` and `./node_modules/.bin/next build` (or `pnpm --filter web test` / `... build` if `pnpm` is on PATH).
- **Commits:** stage with `git add -A -- ':!docs'` for code tasks (the coordinator edits docs concurrently); docs task stages `docs/` + `README.md` explicitly. Author every commit:
  ```
  git -c user.name="Anil Kujur" -c user.email="anilkuj@gmail.com" commit -m "<msg>" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
  ```
  **Do not push.** One commit per task.
- **TDD:** write the failing test, run it, see it fail for the right reason, implement minimally, run it green, then the full suite.
- **Full verification (run before every task commit):** `python -m pytest -q -W error` (repo root — needs Docker), `python -m ruff check .`, `python -m alembic check`. Web tasks also: `./node_modules/.bin/vitest run` and `./node_modules/.bin/next build`.

**Baseline test count:** repo root `python -m pytest -q` is currently **93 passed**. Each task below states the new expected count.

---

## File Structure

| File | Responsibility |
|---|---|
| `packages/live/` (new pkg `fplguru-live`) | Pure bonus math: `project_bonus` (one fixture's BPS → 3/2/1 with FPL tie rules) and `build_live_rows` (`event/{gw}/live` payload → `player_gw_live` row dicts). No DB, no network. |
| `packages/core/src/fplguru_core/models.py` | `PlayerGwLive` model; `Fixture` gains `started` / `finished_provisional` / `minutes`. |
| `packages/ingest/src/fplguru_ingest/fpl.py` | `normalize_fixtures` emits the three new fixture fields. |
| `alembic/versions/0004_live_scores.py` | Create `player_gw_live`; add the three `fixtures` columns. |
| `services/worker/src/fplguru_worker/tasks.py` | `_poll_live` async helper + `poll_live` Celery task. |
| `services/worker/src/fplguru_worker/app.py` | Beat entry `poll-live`. |
| `packages/core/src/fplguru_core/settings.py` | `live_poll_seconds` (60.0), `live_stream_poll_seconds` (5.0). |
| `services/api/src/fplguru_api/main.py` | `_live_snapshot` helper; `GET /gameweeks/current/live`; `GET /gameweeks/current/live/stream`; `"live_poll"` added to `/status` known sources. |
| `apps/web/src/lib/api.ts` | `LiveFixture` / `LivePlayer` / `LiveSnapshot` types + `getLive`. |
| `apps/web/src/app/live/page.tsx`, `apps/web/src/app/live/LiveBoard.tsx` | GW Live page (server shell + client board with SSE + fallback). |
| `apps/web/src/app/layout.tsx` | Nav: greyed `Live` span → `<a href="/live">`. |

---

## Task 1: `fplguru-live` package — bonus projection math

**Files:**
- Create: `packages/live/pyproject.toml`
- Create: `packages/live/src/fplguru_live/__init__.py`
- Create: `packages/live/tests/test_live.py`
- Modify: `requirements-dev.txt`
- Modify: `pyproject.toml` (ruff `known-first-party`)

- [ ] **Step 1: package skeleton**

`packages/live/pyproject.toml` (copy the shape of `packages/fdr/pyproject.toml`):
```toml
[project]
name = "fplguru-live"
version = "0.0.0"
description = "Pure live-scoring math: BPS bonus projection and event/live row shaping."
requires-python = ">=3.12"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/fplguru_live"]
```

`requirements-dev.txt` — add after the `-e ./packages/fdr` line:
```
-e ./packages/live
```

`pyproject.toml` — add `"fplguru_live"` to `[tool.ruff.lint.isort] known-first-party`:
```toml
known-first-party = [
    "fplguru_core", "fplguru_fpl_client", "fplguru_ingest",
    "fplguru_ml", "fplguru_api", "fplguru_worker", "fplguru_live",
]
```

Then: `python -m pip install -r requirements-dev.txt` → expect `Successfully installed ... fplguru-live-0.0.0 ...`.

- [ ] **Step 2: write the failing test**

`packages/live/tests/test_live.py`:
```python
from fplguru_live import build_live_rows, project_bonus


def test_project_bonus_simple_321():
    # distinct BPS values 30 > 25 > 20 -> 3, 2, 1
    got = project_bonus({1: 30, 2: 25, 3: 20, 4: 10})
    assert got == {1: 3, 2: 2, 3: 1, 4: 0}


def test_project_bonus_tie_for_first_skips_two():
    # two tied on top -> both 3, next distinct -> 1 (no 2 awarded)
    got = project_bonus({1: 30, 2: 30, 3: 25, 4: 25})
    assert got == {1: 3, 2: 3, 3: 1, 4: 1}


def test_project_bonus_tie_for_second_skips_one():
    got = project_bonus({1: 40, 2: 30, 3: 30})
    assert got == {1: 3, 2: 2, 3: 2}


def test_project_bonus_non_positive_bps_gets_nothing():
    got = project_bonus({1: 0, 2: -3, 3: 12})
    assert got == {1: 0, 2: 0, 3: 3}


def test_project_bonus_empty():
    assert project_bonus({}) == {}


_PAYLOAD = {
    "elements": [
        # player 11: two fixtures (DGW) -> bonus summed across both
        {"id": 11, "stats": {"minutes": 90, "total_points": 8, "bps": 55},
         "explain": [
             {"fixture": 100, "stats": [{"identifier": "bps", "value": 30}]},
             {"fixture": 101, "stats": [{"identifier": "bps", "value": 25}]},
         ]},
        # player 12: one fixture, tops fixture 100
        {"id": 12, "stats": {"minutes": 90, "total_points": 6, "bps": 33},
         "explain": [{"fixture": 100, "stats": [{"identifier": "bps", "value": 33}]}]},
        # player 13: one fixture, below player 11 in fixture 101
        {"id": 13, "stats": {"minutes": 45, "total_points": 2, "bps": 10},
         "explain": [{"fixture": 101, "stats": [{"identifier": "bps", "value": 10}]}]},
        # player 14: did not feature -> no row
        {"id": 14, "stats": {"minutes": 0, "total_points": 0, "bps": 0}, "explain": []},
    ]
}


def test_build_live_rows_projects_and_sums_bonus():
    rows = {r["player_id"]: r for r in build_live_rows(3, _PAYLOAD)}
    assert set(rows) == {11, 12, 13}  # 14 excluded

    # fixture 100: bps 33 (p12) > 30 (p11) -> p12=3, p11=2
    # fixture 101: bps 25 (p11) > 10 (p13) -> p11=3, p13=2
    assert rows[11]["projected_bonus"] == 2 + 3
    assert rows[12]["projected_bonus"] == 3
    assert rows[13]["projected_bonus"] == 2

    assert rows[11]["gameweek_id"] == 3
    assert rows[11]["minutes"] == 90
    assert rows[11]["live_points"] == 8
    assert rows[11]["bps"] == 55
    assert rows[11]["total_points"] == 8 + 5  # live_points + projected_bonus


def test_build_live_rows_without_explain_uses_stats_bps_single_bucket():
    payload = {"elements": [
        {"id": 21, "stats": {"minutes": 90, "total_points": 5, "bps": 40}},
        {"id": 22, "stats": {"minutes": 90, "total_points": 3, "bps": 20}},
    ]}
    rows = {r["player_id"]: r for r in build_live_rows(3, payload)}
    # no explain -> all such players share one synthetic bucket, ranked by stats.bps
    assert rows[21]["projected_bonus"] == 3
    assert rows[22]["projected_bonus"] == 2
```

Run: `python -m pytest packages/live/tests/test_live.py -q` → FAIL (`ModuleNotFoundError: fplguru_live`).

- [ ] **Step 3: implement `packages/live/src/fplguru_live/__init__.py`**

```python
"""Pure live-scoring math — no DB, no network.

`project_bonus`  : one fixture's {player_id: bps} -> {player_id: 0|1|2|3}
`build_live_rows`: an event/{gw}/live payload -> player_gw_live row dicts
"""
from __future__ import annotations

from typing import Any

__all__ = ["project_bonus", "build_live_rows"]

_SYNTHETIC_FIXTURE = -1


def project_bonus(bps_by_player: dict[int, int]) -> dict[int, int]:
    """Provisional FPL bonus, by *rank position* (standard competition ranking).
    Rank 0 (highest BPS) -> 3, rank 1 -> 2, rank 2 -> 1, below that -> 0. Tied
    players share a rank, so a tie for a place consumes the place(s) below it
    (e.g. BPS 30, 30, 25 -> 3, 3, 1). Only positive BPS is eligible."""
    if not bps_by_player:
        return {}
    positives = [b for b in bps_by_player.values() if b > 0]
    by_rank = {0: 3, 1: 2, 2: 1}
    award: dict[int, int] = {}
    for pid, b in bps_by_player.items():
        if b <= 0:
            award[pid] = 0
            continue
        rank = sum(1 for v in positives if v > b)
        award[pid] = by_rank.get(rank, 0)
    return award


def _bps_from_explain(entry: dict[str, Any]) -> int:
    for item in entry.get("stats", []):
        if item.get("identifier") == "bps":
            return int(item.get("value", 0))
    return 0


def build_live_rows(gameweek_id: int, payload: dict[str, Any]) -> list[dict]:
    by_fixture: dict[int, dict[int, int]] = {}
    meta: dict[int, tuple[int, int, int]] = {}  # pid -> (minutes, live_points, bps_total)

    for el in payload.get("elements", []):
        pid = el["id"]
        s = el.get("stats", {})
        minutes = int(s.get("minutes", 0))
        bps_total = int(s.get("bps", 0))
        explain = el.get("explain") or []
        if minutes == 0 and bps_total == 0 and not explain:
            continue
        meta[pid] = (minutes, int(s.get("total_points", 0)), bps_total)
        if explain:
            for e in explain:
                by_fixture.setdefault(int(e["fixture"]), {})[pid] = _bps_from_explain(e)
        else:
            by_fixture.setdefault(_SYNTHETIC_FIXTURE, {})[pid] = bps_total

    awards: dict[int, int] = {}
    for bps_map in by_fixture.values():
        for pid, bonus in project_bonus(bps_map).items():
            awards[pid] = awards.get(pid, 0) + bonus

    rows: list[dict] = []
    for pid, (minutes, live_points, bps_total) in meta.items():
        pb = awards.get(pid, 0)
        rows.append({
            "player_id": pid,
            "gameweek_id": gameweek_id,
            "minutes": minutes,
            "live_points": live_points,
            "bps": bps_total,
            "projected_bonus": pb,
            "total_points": live_points + pb,
        })
    return rows
```

- [ ] **Step 4: run tests green**

`python -m pytest packages/live/tests/test_live.py -q` → **7 passed**.

- [ ] **Step 5: full verification + commit**

`python -m pytest -q -W error` → **100 passed** (93 + 7), no warnings.
`python -m ruff check .` → clean. `python -m alembic check` → clean.
```bash
git add -A -- ':!docs'
git -c user.name="Anil Kujur" -c user.email="anilkuj@gmail.com" commit -m "feat(live): fplguru-live — BPS bonus projection + event/live row shaping" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2: `player_gw_live` model + `Fixture` match-state columns + `0004` migration

**Files:**
- Modify: `packages/core/src/fplguru_core/models.py`
- Modify: `packages/ingest/src/fplguru_ingest/fpl.py` (`normalize_fixtures`)
- Modify: `packages/ingest/tests/test_fpl_normalizers.py`
- Modify: `packages/ingest/tests/fixtures/fixtures_sample.json`
- Modify: `packages/core/tests/test_models.py`
- Create: `alembic/versions/0004_live_scores.py`
- Create: `packages/core/tests/test_live_model.py`

- [ ] **Step 1: failing tests**

`packages/core/tests/test_live_model.py`:
```python
from fplguru_core.models import Base, Fixture, PlayerGwLive


def test_player_gw_live_registered_with_unique_key():
    assert "player_gw_live" in Base.metadata.tables
    uqs = {
        tuple(sorted(c.name for c in con.columns))
        for con in PlayerGwLive.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    }
    assert ("gameweek_id", "player_id") in uqs


def test_fixture_has_match_state_columns():
    cols = {c.name for c in Fixture.__table__.columns}
    assert {"started", "finished_provisional", "minutes"} <= cols
```

Append to `packages/ingest/tests/test_fpl_normalizers.py::test_normalize_fixtures_handles_null_event_and_kickoff` (add assertions) — or add a new test:
```python
def test_normalize_fixtures_carries_match_state():
    rows = normalize_fixtures(FIXTURES)
    assert rows[0]["started"] is True
    assert rows[0]["minutes"] == 63
    assert rows[0]["finished_provisional"] is False
    # missing keys default safely
    assert rows[1]["started"] is False
    assert rows[1]["minutes"] == 0
```

`packages/ingest/tests/fixtures/fixtures_sample.json` — add the new keys to the **first** object only (leave the second without them to prove the defaults):
```json
[
  {"id": 1, "event": 1, "kickoff_time": "2025-08-16T14:00:00Z",
   "team_h": 1, "team_a": 1, "team_h_difficulty": 3, "team_a_difficulty": 2,
   "finished": false, "team_h_score": null, "team_a_score": null,
   "started": true, "minutes": 63, "finished_provisional": false},
  {"id": 2, "event": null, "kickoff_time": null,
   "team_h": 1, "team_a": 1, "team_h_difficulty": 4, "team_a_difficulty": 4,
   "finished": false, "team_h_score": null, "team_a_score": null}
]
```

`packages/core/tests/test_models.py` — add `"player_gw_live"` to the expected set:
```python
    assert set(Base.metadata.tables) == {
        "teams", "gameweeks", "players", "fixtures", "data_sync_log",
        "player_gw_stats", "player_gw_features", "player_gw_predictions",
        "linked_teams", "entry_gw_history", "entry_picks",
        "player_gw_live",
    }
```

Run: `python -m pytest packages/core/tests/test_live_model.py packages/ingest/tests/test_fpl_normalizers.py -q` → FAIL (`ImportError: PlayerGwLive`, missing keys).

- [ ] **Step 2: model changes in `packages/core/src/fplguru_core/models.py`**

In `class Fixture`, after `away_score`:
```python
    started: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    finished_provisional: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
```

Add a new model directly after `class PlayerGwStat` (keep the file's ordering: stats → live):
```python
class PlayerGwLive(_TimestampMixin, Base):
    """Provisional in-play scoring for the current gameweek: live points
    (excl. bonus) + a BPS-derived bonus projection. Superseded by
    player_gw_stats once the gameweek is finished."""
    __tablename__ = "player_gw_live"
    __table_args__ = (
        UniqueConstraint("player_id", "gameweek_id",
                         name="uq_player_gw_live_player_id_gameweek_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    live_points: Mapped[int] = mapped_column(Integer, default=0)  # excludes bonus
    bps: Mapped[int] = mapped_column(Integer, default=0)
    projected_bonus: Mapped[int] = mapped_column(Integer, default=0)
    total_points: Mapped[int] = mapped_column(Integer, default=0)  # live_points + projected_bonus
```

- [ ] **Step 3: `normalize_fixtures` in `packages/ingest/src/fplguru_ingest/fpl.py`**

Add three keys to the returned dict:
```python
            "finished": bool(f["finished"]),
            "home_score": f.get("team_h_score"),
            "away_score": f.get("team_a_score"),
            "started": bool(f.get("started", False)),
            "finished_provisional": bool(f.get("finished_provisional", False)),
            "minutes": int(f.get("minutes", 0) or 0),
```

- [ ] **Step 4: migration `alembic/versions/0004_live_scores.py`**

```python
"""live scores

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'player_gw_live',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('gameweek_id', sa.Integer(), nullable=False),
        sa.Column('minutes', sa.Integer(), nullable=False),
        sa.Column('live_points', sa.Integer(), nullable=False),
        sa.Column('bps', sa.Integer(), nullable=False),
        sa.Column('projected_bonus', sa.Integer(), nullable=False),
        sa.Column('total_points', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['gameweek_id'], ['gameweeks.id'],
                                name=op.f('fk_player_gw_live_gameweek_id_gameweeks')),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'],
                                name=op.f('fk_player_gw_live_player_id_players')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_player_gw_live')),
        sa.UniqueConstraint('player_id', 'gameweek_id',
                            name='uq_player_gw_live_player_id_gameweek_id'),
    )
    op.create_index(op.f('ix_player_gw_live_gameweek_id'), 'player_gw_live',
                    ['gameweek_id'], unique=False)
    op.create_index(op.f('ix_player_gw_live_player_id'), 'player_gw_live',
                    ['player_id'], unique=False)

    op.add_column('fixtures', sa.Column('started', sa.Boolean(), nullable=False,
                                        server_default=sa.text('false')))
    op.add_column('fixtures', sa.Column('finished_provisional', sa.Boolean(), nullable=False,
                                        server_default=sa.text('false')))
    op.add_column('fixtures', sa.Column('minutes', sa.Integer(), nullable=False,
                                        server_default=sa.text('0')))


def downgrade() -> None:
    op.drop_column('fixtures', 'minutes')
    op.drop_column('fixtures', 'finished_provisional')
    op.drop_column('fixtures', 'started')
    op.drop_index(op.f('ix_player_gw_live_player_id'), table_name='player_gw_live')
    op.drop_index(op.f('ix_player_gw_live_gameweek_id'), table_name='player_gw_live')
    op.drop_table('player_gw_live')
```

- [ ] **Step 5: apply + verify migration is drift-free**

```bash
python -m alembic upgrade head
python -m alembic check          # -> "No new upgrade operations detected."
```
If `alembic check` reports differences, adjust the migration (usual causes: `server_default` text mismatch on the bool columns — match `sa.text('false')` to the model's `server_default="false"`; column order).

- [ ] **Step 6: tests green + full verification + commit**

`python -m pytest packages/core packages/ingest -q` → all pass.
`python -m pytest -q -W error` → **103 passed** (100 + 3 new: 2 in `test_live_model.py`, 1 in `test_fpl_normalizers.py`), no warnings.
`python -m ruff check .` → clean. `python -m alembic check` → clean.
```bash
git add -A -- ':!docs'
git -c user.name="Anil Kujur" -c user.email="anilkuj@gmail.com" commit -m "feat(core): player_gw_live table + fixture match-state columns (0004)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: worker `poll_live` task + Beat wiring

**Files:**
- Modify: `packages/core/src/fplguru_core/settings.py`
- Modify: `services/worker/src/fplguru_worker/tasks.py`
- Modify: `services/worker/src/fplguru_worker/app.py`
- Create: `services/worker/tests/test_poll_live.py`

- [ ] **Step 1: settings**

In `fplguru_core/settings.py` `Settings`, add (near the other scalars, keep alphabetical-ish grouping with existing fields):
```python
    live_poll_seconds: float = 60.0          # Beat cadence for poll_live
    live_stream_poll_seconds: float = 5.0     # how often the SSE endpoint re-reads the DB
```
(These are plain pydantic-settings fields; env vars `LIVE_POLL_SECONDS` / `LIVE_STREAM_POLL_SECONDS` override them, consistent with the existing settings.)

- [ ] **Step 2: failing test**

`services/worker/tests/test_poll_live.py`:
```python
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from fplguru_core.models import Fixture, Gameweek, Player, PlayerGwLive, Team
from fplguru_worker import tasks

_LIVE_PAYLOAD = {
    "elements": [
        {"id": 1, "stats": {"minutes": 90, "total_points": 9, "bps": 40},
         "explain": [{"fixture": 500, "stats": [{"identifier": "bps", "value": 40}]}]},
        {"id": 2, "stats": {"minutes": 90, "total_points": 4, "bps": 22},
         "explain": [{"fixture": 500, "stats": [{"identifier": "bps", "value": 22}]}]},
        {"id": 3, "stats": {"minutes": 0, "total_points": 0, "bps": 0}, "explain": []},
    ]
}


class _FakeClient:
    def __init__(self, base, *, fixtures, live):
        self._fixtures = fixtures
        self._live = live
    async def fixtures(self):
        return self._fixtures
    async def event_live(self, gw):
        return self._live
    async def aclose(self):
        pass


async def _seed(db_session, *, started):
    db_session.add_all([
        Team(id=1, name="A", short_name="AAA", strength_overall_home=3, strength_overall_away=3),
        Team(id=2, name="B", short_name="BBB", strength_overall_home=3, strength_overall_away=3),
    ])
    db_session.add(Gameweek(id=3, name="GW3", deadline_time=datetime(2025, 9, 1, tzinfo=UTC),
                            is_current=True))
    await db_session.commit()
    db_session.add_all([
        Player(id=1, team_id=1, first_name="p", second_name="one", web_name="P1",
               position="MID", now_cost=70, status="a"),
        Player(id=2, team_id=2, first_name="p", second_name="two", web_name="P2",
               position="DEF", now_cost=50, status="a"),
        Player(id=3, team_id=2, first_name="p", second_name="three", web_name="P3",
               position="FWD", now_cost=60, status="a"),
    ])
    await db_session.commit()
    return [{"id": 500, "event": 3, "kickoff_time": "2025-09-01T14:00:00Z",
             "team_h": 1, "team_a": 2, "team_h_difficulty": 3, "team_a_difficulty": 3,
             "finished": False, "team_h_score": 1, "team_a_score": 0,
             "started": started, "minutes": 70 if started else 0,
             "finished_provisional": False}]


@pytest.mark.asyncio
async def test_poll_live_writes_projection_when_match_in_play(db_session, monkeypatch):
    fixtures = await _seed(db_session, started=True)
    monkeypatch.setattr(tasks, "FplClient",
                        lambda base: _FakeClient(base, fixtures=fixtures, live=_LIVE_PAYLOAD))
    await tasks._poll_live()

    rows = {r.player_id: r for r in (await db_session.execute(select(PlayerGwLive))).scalars()}
    assert set(rows) == {1, 2}                       # player 3 did not feature
    assert rows[1].projected_bonus == 3             # top BPS in fixture 500
    assert rows[2].projected_bonus == 2
    assert rows[1].total_points == 9 + 3
    # fixture score / state mirrored into the fixtures table
    fx = (await db_session.execute(select(Fixture).where(Fixture.id == 500))).scalar_one()
    assert fx.started is True and fx.home_score == 1 and fx.minutes == 70


@pytest.mark.asyncio
async def test_poll_live_noop_when_no_match_in_play(db_session, monkeypatch):
    fixtures = await _seed(db_session, started=False)
    monkeypatch.setattr(tasks, "FplClient",
                        lambda base: _FakeClient(base, fixtures=fixtures, live=_LIVE_PAYLOAD))
    await tasks._poll_live()

    assert (await db_session.execute(select(PlayerGwLive))).first() is None
```

Run: `python -m pytest services/worker/tests/test_poll_live.py -q` → FAIL (`AttributeError: _poll_live`).

- [ ] **Step 3: implement in `services/worker/src/fplguru_worker/tasks.py`**

Add imports: extend the `fplguru_core.models` import with `PlayerGwLive`; add `from fplguru_live import build_live_rows`.

Add an upsert helper (mirrors `_upsert_stats`), then the task helper + task. Place `_poll_live` after `_sync_gw_stats` and its task after `sync_gw_stats`:
```python
async def _upsert_live(session, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(PlayerGwLive).values(rows)
    update_cols = {
        c: stmt.excluded[c] for c in rows[0] if c not in ("player_id", "gameweek_id")
    }
    update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(
        index_elements=["player_id", "gameweek_id"], set_=update_cols
    )
    await session.execute(stmt)


async def _poll_live() -> None:
    started = datetime.now(UTC)
    try:
        async with get_sessionmaker()() as session:
            gw = (
                await session.execute(select(Gameweek).where(Gameweek.is_current))
            ).scalar_one_or_none()
        if gw is None:
            async with get_sessionmaker()() as session, session.begin():
                await _record(session, "live_poll", "ok", started, "no current gameweek")
            return

        client = FplClient(get_settings().fpl_api_base)
        try:
            all_fixtures = await client.fixtures()
            gw_fixtures = [f for f in all_fixtures if f.get("event") == gw.id]
            live = [f for f in gw_fixtures if f.get("started") and not f.get("finished")]
            payload = await client.event_live(gw.id) if live else None
        finally:
            await client.aclose()

        async with get_sessionmaker()() as session, session.begin():
            await _upsert(session, Fixture, normalize_fixtures(gw_fixtures))
            if payload is None:
                await _record(session, "live_poll", "ok", started, "no live fixtures")
                return
            rows = build_live_rows(gw.id, payload)
            await _upsert_live(session, rows)
            await _record(session, "live_poll", "ok", started, f"{len(rows)} rows")
        logger.info("live poll: %d players over %d live fixtures", len(rows), len(live))
    except Exception as exc:
        await _log_error("live_poll", started, exc)
        raise


@celery_app.task(name="poll_live", bind=True, max_retries=2, default_retry_delay=30)
def poll_live(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_poll_live))
    except Exception as exc:
        raise self.retry(exc=exc) from exc
```

- [ ] **Step 4: Beat wiring in `services/worker/src/fplguru_worker/app.py`**

Add to `beat_schedule`:
```python
        "poll-live": {"task": "poll_live", "schedule": settings.live_poll_seconds},
```

- [ ] **Step 5: tests green + full verification + commit**

`python -m pytest services/worker/tests/test_poll_live.py -q` → **2 passed**.
`python -m pytest -q -W error` → **105 passed** (103 + 2), no warnings.
`python -m ruff check .` → clean. `python -m alembic check` → clean.
```bash
git add -A -- ':!docs'
git -c user.name="Anil Kujur" -c user.email="anilkuj@gmail.com" commit -m "feat(worker): poll_live task — in-play BPS bonus projection on a Beat cadence" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: API `GET /gameweeks/current/live` snapshot

**Files:**
- Modify: `services/api/src/fplguru_api/main.py`
- Modify: `services/api/pyproject.toml`
- Create: `services/api/tests/test_live_api.py`

- [ ] **Step 1: deps**

`services/api/pyproject.toml` — add `"fplguru-live"` to `dependencies` (alongside `"fplguru-fdr"`). Run `python -m pip install -r requirements-dev.txt`.

- [ ] **Step 2: failing test**

`services/api/tests/test_live_api.py`:
```python
from datetime import UTC, datetime

from fplguru_core.models import Fixture, Gameweek, Player, PlayerGwLive, Team


async def _seed(db_session):
    db_session.add_all([
        Team(id=1, name="A", short_name="AAA", strength_overall_home=3, strength_overall_away=3),
        Team(id=2, name="B", short_name="BBB", strength_overall_home=3, strength_overall_away=3),
    ])
    db_session.add(Gameweek(id=3, name="GW3", deadline_time=datetime(2025, 9, 1, tzinfo=UTC),
                            is_current=True))
    await db_session.commit()
    db_session.add_all([
        Player(id=1, team_id=1, first_name="p", second_name="one", web_name="P1",
               position="MID", now_cost=70, status="a"),
        Player(id=2, team_id=2, first_name="p", second_name="two", web_name="P2",
               position="DEF", now_cost=50, status="a"),
        Fixture(id=500, gameweek_id=3, home_team_id=1, away_team_id=2, home_difficulty=3,
                away_difficulty=3, finished=False, home_score=1, away_score=0,
                started=True, minutes=70),
    ])
    await db_session.commit()
    db_session.add_all([
        PlayerGwLive(player_id=1, gameweek_id=3, minutes=90, live_points=9, bps=40,
                     projected_bonus=3, total_points=12),
        PlayerGwLive(player_id=2, gameweek_id=3, minutes=90, live_points=4, bps=22,
                     projected_bonus=2, total_points=6),
    ])
    await db_session.commit()


async def test_live_snapshot_ranks_players_and_lists_fixtures(client, db_session):
    await _seed(db_session)
    body = (await client.get("/gameweeks/current/live")).json()
    assert body["gameweek_id"] == 3
    assert body["updated_at"] is not None
    assert [p["player_id"] for p in body["players"]] == [1, 2]   # total_points desc
    assert body["players"][0]["projected_bonus"] == 3
    assert body["players"][0]["web_name"] == "P1"
    assert body["fixtures"][0]["id"] == 500
    assert body["fixtures"][0]["started"] is True
    assert body["fixtures"][0]["home_score"] == 1


async def test_live_snapshot_empty_when_no_current_gameweek(client, db_session):
    body = (await client.get("/gameweeks/current/live")).json()
    assert body == {"gameweek_id": None, "updated_at": None, "fixtures": [], "players": []}
```

Run: `python -m pytest services/api/tests/test_live_api.py -q` → FAIL (404).

- [ ] **Step 3: implement in `main.py`**

Extend the `fplguru_core.models` import with `PlayerGwLive` (and `Fixture`, `Player` if not already imported — check; `Team`/`Fixture` were added in P1d, `Player` is present from P1c). Add near the other gameweek routes:
```python
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
```

Also add `"live_poll"` to the `/status` `known` set:
```python
    known = {"fpl_bootstrap", "fpl_fixtures", "live_poll"}
```

- [ ] **Step 4: tests green + full verification + commit**

`python -m pytest services/api/tests/test_live_api.py -q` → **2 passed**.
`python -m pytest -q -W error` → **107 passed** (105 + 2), no warnings.
`python -m ruff check .` → clean. `python -m alembic check` → clean.
```bash
git add -A -- ':!docs'
git -c user.name="Anil Kujur" -c user.email="anilkuj@gmail.com" commit -m "feat(api): GET /gameweeks/current/live snapshot (ranked live points + bonus projection)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: API `GET /gameweeks/current/live/stream` (SSE)

**Files:**
- Modify: `services/api/src/fplguru_api/main.py`
- Modify: `services/api/tests/test_live_api.py`

- [ ] **Step 1: failing test** — append to `services/api/tests/test_live_api.py`:
```python
import json


async def test_live_stream_emits_a_snapshot_event(client, db_session):
    await _seed(db_session)
    async with client.stream("GET", "/gameweeks/current/live/stream") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        got = None
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                got = json.loads(line[len("data: "):])
                break
    assert got is not None
    assert got["gameweek_id"] == 3
    assert got["players"][0]["player_id"] == 1
```

Run → FAIL (404).

- [ ] **Step 2: implement in `main.py`**

Add imports: `import asyncio`, `import json` at the top with the stdlib imports (check — `asyncio`/`json` may not be imported yet); `from fastapi.responses import StreamingResponse`; `from fplguru_core.db import get_sessionmaker`.

```python
async def _live_event_stream(request: Request, poll_seconds: float):
    sentinel = object()
    last: object = sentinel
    while True:
        if await request.is_disconnected():
            break
        async with get_sessionmaker()() as db:
            snap = await _live_snapshot(db)
        if snap["updated_at"] != last:
            last = snap["updated_at"]
            yield f"data: {json.dumps(snap)}\n\n"
        else:
            yield ": keepalive\n\n"
        await asyncio.sleep(poll_seconds)


@app.get("/gameweeks/current/live/stream")
async def live_stream(request: Request) -> StreamingResponse:
    poll_seconds = get_settings().live_stream_poll_seconds
    return StreamingResponse(
        _live_event_stream(request, poll_seconds),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```
Add `Request` to the `from fastapi import ...` line. Add `from fplguru_core.settings import get_settings` if not already imported (it is used elsewhere — check).

Note: the first loop iteration always emits a `data:` event (sentinel `!=` any real value), so a client — and the test — gets a snapshot immediately; the `asyncio.sleep` is only reached after the first event. The test breaks out after that first event, so it never blocks on the poll interval.

- [ ] **Step 3: tests green + full verification + commit**

`python -m pytest services/api/tests/test_live_api.py -q` → **3 passed**.
`python -m pytest -q -W error` → **108 passed** (107 + 1), no warnings.
`python -m ruff check .` → clean. `python -m alembic check` → clean.
```bash
git add -A -- ':!docs'
git -c user.name="Anil Kujur" -c user.email="anilkuj@gmail.com" commit -m "feat(api): SSE stream GET /gameweeks/current/live/stream" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 6: web — `getLive` client + types

**Files:**
- Modify: `apps/web/src/lib/api.ts`
- Create: `apps/web/src/lib/api.live.test.ts`

- [ ] **Step 1: failing test** — `apps/web/src/lib/api.live.test.ts`:
```ts
import { describe, expect, it, vi } from "vitest";

import { getLive } from "./api";

describe("getLive", () => {
  it("fetches the current-GW live snapshot", async () => {
    const snap = {
      gameweek_id: 3,
      updated_at: "2026-08-27T14:00:00+00:00",
      fixtures: [],
      players: [],
    };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => snap });
    global.fetch = fetchMock as unknown as typeof fetch;

    const r = await getLive("http://api.test");
    expect(r.gameweek_id).toBe(3);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/gameweeks/current/live");
  });
});
```

Run: `cd apps/web && ./node_modules/.bin/vitest run src/lib/api.live.test.ts` → FAIL (`getLive` is not exported).

- [ ] **Step 2: implement** — append to `apps/web/src/lib/api.ts`:
```ts
export type LiveFixture = {
  id: number;
  home_team_id: number;
  away_team_id: number;
  home_score: number | null;
  away_score: number | null;
  started: boolean;
  finished: boolean;
  minutes: number;
};
export type LivePlayer = {
  player_id: number;
  web_name: string;
  team_id: number;
  position: string;
  minutes: number;
  live_points: number;
  bps: number;
  projected_bonus: number;
  total_points: number;
};
export type LiveSnapshot = {
  gameweek_id: number | null;
  updated_at: string | null;
  fixtures: LiveFixture[];
  players: LivePlayer[];
};

export function getLive(base: string) {
  return fetch(`${base}/gameweeks/current/live`, { cache: "no-store" }).then(
    asJson<LiveSnapshot>,
  );
}
```

- [ ] **Step 3: green + commit**

`./node_modules/.bin/vitest run` → all pass (was 4, now 5).
```bash
cd .. && git add -A -- ':!docs'
git -c user.name="Anil Kujur" -c user.email="anilkuj@gmail.com" commit -m "feat(web): getLive client + live snapshot types" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 7: web — `/live` page (SSE board + fallback) + nav link

**Files:**
- Create: `apps/web/src/app/live/page.tsx`
- Create: `apps/web/src/app/live/LiveBoard.tsx`
- Modify: `apps/web/src/app/layout.tsx`

- [ ] **Step 1: `apps/web/src/app/live/page.tsx`** (server shell, mirrors `squad/page.tsx`):
```tsx
import { LiveBoard } from "./LiveBoard";

export default function LivePage() {
  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">GW Live</h1>
      <LiveBoard />
    </main>
  );
}
```

- [ ] **Step 2: `apps/web/src/app/live/LiveBoard.tsx`** (client):
```tsx
"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { getEntry, getLive, type LiveSnapshot } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function LiveBoard() {
  const [snap, setSnap] = useState<LiveSnapshot | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [mineOnly, setMineOnly] = useState(false);
  const [squad, setSquad] = useState<Set<number> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // one-time: my squad (for the "my players" filter)
  useEffect(() => {
    const id = getStoredEntryId();
    if (id == null) return;
    getEntry(API, id)
      .then((e) => setSquad(new Set(e.picks.map((p) => p.player_id))))
      .catch(() => setSquad(null));
  }, []);

  // live data: SSE, with a polling fallback if the stream errors
  useEffect(() => {
    let closed = false;
    getLive(API).then(setSnap).catch(() => undefined);

    const startPolling = () => {
      if (pollRef.current) return;
      pollRef.current = setInterval(() => {
        getLive(API)
          .then((s) => {
            setSnap(s);
            setErr(null);
          })
          .catch(() => setErr("Live updates unavailable — retrying."));
      }, 15000);
    };

    let es: EventSource | null = null;
    try {
      es = new EventSource(`${API}/gameweeks/current/live/stream`);
      es.onmessage = (ev) => {
        if (closed) return;
        try {
          setSnap(JSON.parse(ev.data) as LiveSnapshot);
          setErr(null);
        } catch {
          /* ignore keepalive / partial */
        }
      };
      es.onerror = () => {
        es?.close();
        startPolling();
      };
    } catch {
      startPolling();
    }

    return () => {
      closed = true;
      es?.close();
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, []);

  const players = useMemo(() => {
    const all = snap?.players ?? [];
    return mineOnly && squad ? all.filter((p) => squad.has(p.player_id)) : all;
  }, [snap, mineOnly, squad]);

  if (!snap) return <p className="mt-4 text-sm text-gray-500">Loading…</p>;
  if (snap.gameweek_id == null)
    return <p className="mt-4 text-sm text-gray-500">No active gameweek.</p>;

  return (
    <>
      <div className="mt-2 flex items-center gap-3 text-sm text-gray-500">
        <span>
          GW{snap.gameweek_id}
          {snap.updated_at
            ? ` · updated ${new Date(snap.updated_at).toLocaleTimeString()}`
            : " · no live data yet"}
        </span>
        {squad && (
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={mineOnly}
              onChange={(e) => setMineOnly(e.target.checked)}
            />
            My players
          </label>
        )}
      </div>
      {err && <p className="mt-2 text-sm text-amber-600">{err}</p>}

      <div className="mt-4 flex flex-wrap gap-2">
        {snap.fixtures.map((f) => (
          <span key={f.id} className="rounded border px-2 py-1 text-sm">
            {f.home_team_id}&nbsp;
            {f.started ? (f.home_score ?? 0) : "–"}
            {" - "}
            {f.started ? (f.away_score ?? 0) : "–"}&nbsp;{f.away_team_id}
            <span className="ml-1 text-gray-400">
              {f.finished ? "FT" : f.started ? `${f.minutes}'` : ""}
            </span>
          </span>
        ))}
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="text-sm border-collapse">
          <thead>
            <tr className="text-left">
              <th className="px-2 py-1">Player</th>
              <th className="px-2 py-1">Pos</th>
              <th className="px-2 py-1 text-right">Min</th>
              <th className="px-2 py-1 text-right">Pts</th>
              <th className="px-2 py-1 text-right">Bonus*</th>
              <th className="px-2 py-1 text-right">BPS</th>
              <th className="px-2 py-1 text-right">Total</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p) => (
              <tr key={p.player_id} className="border-t">
                <td className="px-2 py-1 font-medium">{p.web_name}</td>
                <td className="px-2 py-1 text-gray-500">{p.position}</td>
                <td className="px-2 py-1 text-right">{p.minutes}</td>
                <td className="px-2 py-1 text-right">{p.live_points}</td>
                <td className="px-2 py-1 text-right text-gray-500">
                  {p.projected_bonus ? `+${p.projected_bonus}` : "—"}
                </td>
                <td className="px-2 py-1 text-right text-gray-400">{p.bps}</td>
                <td className="px-2 py-1 text-right font-semibold">{p.total_points}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-gray-400">
        *Bonus is a live BPS projection and can change until fixtures are final.
      </p>
    </>
  );
}
```

- [ ] **Step 3: nav link** — in `apps/web/src/app/layout.tsx` replace `<span className="text-gray-400">Live</span>` with `<a href="/live">Live</a>`.

- [ ] **Step 4: verify build + commit**

`cd apps/web && ./node_modules/.bin/vitest run` → 5 pass (unchanged).
`./node_modules/.bin/next build` → success; route list shows `○ /live` (static; data is fetched client-side).
```bash
cd .. && git add -A -- ':!docs'
git -c user.name="Anil Kujur" -c user.email="anilkuj@gmail.com" commit -m "feat(web): GW Live page — SSE board with polling fallback + my-players filter" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 8: docs

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-08-27-fplguru-master-build-plan.md`
- Modify: `docs/RESUME-foundation.md`

- [ ] **Step 1: `README.md`** — under the API list line add `/gameweeks/current/live[/stream]`; add a section after the "Fixture difficulty (FDR)" section:
```markdown
## GW Live

During matches a `poll_live` worker task (Beat cadence `LIVE_POLL_SECONDS`, default 60)
pulls `event/{gw}/live`, projects provisional 3/2/1 bonus per fixture from BPS, and writes
`player_gw_live`. The web `/live` page subscribes over SSE and falls back to polling.

```bash
#   GET /gameweeks/current/live         -> ranked live points + bonus projection + fixtures
#   GET /gameweeks/current/live/stream  -> text/event-stream; a new snapshot on each change
```
Bonus is a live projection and can change until fixtures are final; finished-GW scoring is
served from `player_gw_stats` (the xP/actuals path), not this table.
```
Also add `poll_live` to the worker/Beat description if one is listed.

- [ ] **Step 2: master plan** — mark **P1b** ✅ in the Phase 1 table with a one-line summary (branch `feature/p1b-live-scores`): `player_gw_live` + `fixtures` match-state cols (`0004`); `fplguru-live` bonus-projection pkg; `poll_live` Beat task (in-play only); `GET /gameweeks/current/live` + `/stream` (SSE); Next.js `/live` board with polling fallback + my-players filter. Decrement the "Remaining sub-plans" count in the scope-override banner (16 → 15).

- [ ] **Step 3: `docs/RESUME-foundation.md`** — update the top status line (P1b in progress → done on merge) and add a `## P1b — Live Scores & GW Live` section with a task table (Tasks 1–8, commits) mirroring the P1d section, plus the live-verification note placeholder. Update the "Remaining unblocked Phase-1 path" line to `P1e → P1f → P1h`.

- [ ] **Step 4: full verification**

`python -m pytest -q -W error` → **108 passed**, no warnings · `python -m ruff check .` → clean · `python -m alembic check` → clean · `cd apps/web && ./node_modules/.bin/vitest run` → 5 passed · `./node_modules/.bin/next build` → success.

- [ ] **Step 5: commit**
```bash
git add -- docs README.md
git -c user.name="Anil Kujur" -c user.email="anilkuj@gmail.com" commit -m "docs: P1b Live Scores & GW Live complete" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage (master §3 P1b / PRD §4.10 GW Live, §7):**
- Per-player live points during matches → `poll_live` + `player_gw_live.live_points` (Tasks 2–3) ✓
- BPS-based bonus projection → `fplguru-live.project_bonus` with FPL tie rules, per-fixture, DGW-summed (Tasks 1, 3) ✓
- Dashboard updates within ~10s (SSE) → `GET /.../live/stream`, re-reads DB every `live_stream_poll_seconds` (5s); end-to-end latency ≈ that + `live_poll_seconds` (60s upstream) + FPL's own lag. The 60s upstream cadence is a settable floor — note this limitation in the RESUME doc; a shorter interval is a one-line settings change (Task 5) ✓ (partial — cadence-bound, documented)
- GW Live tool page → `/live` route with fixtures strip + ranked board + my-players filter (Task 7) ✓
- Graceful degradation (§7) → `poll_live` is a no-op with an `ok` audit row when no match is in play; SSE endpoint degrades to a client-side 15s poll on error; snapshot returns an empty shape when there is no current GW (Tasks 3–7) ✓

**Type/name consistency:**
- `build_live_rows(gameweek_id, payload) -> list[dict]` — Task 1 def == Task 3 call ✓
- row dict keys `player_id, gameweek_id, minutes, live_points, bps, projected_bonus, total_points` == `PlayerGwLive` columns == `_upsert_live` conflict-safe set == snapshot JSON == web `LivePlayer` (minus the joined `web_name/team_id/position`) ✓
- `PlayerGwLive` unique key `(player_id, gameweek_id)` == `_upsert_live` `index_elements` == migration `UniqueConstraint` name `uq_player_gw_live_player_id_gameweek_id` ✓
- `normalize_fixtures` new keys `started/finished_provisional/minutes` == `Fixture` new columns == migration `add_column`s ✓
- `_live_snapshot` shape identical between the snapshot route and the SSE generator (single helper) ✓
- Settings `live_poll_seconds` (Beat) / `live_stream_poll_seconds` (SSE) — defined Task 3, consumed Tasks 3 & 5 ✓

**Migration drift:** `0004` adds one table + three columns; Task 2 Step 5 runs `alembic check` explicitly; `test_expected_tables_registered` updated in the same task. Bool `server_default` is `sa.text('false')` in the migration to match `server_default="false"` on the model.

**Placeholder scan:** none — all code is complete inline.

---

## Execution Handoff

Branch `feature/p1b-live-scores` off `main`. Subagent-driven, order 1 → 8. Task 1 (bonus math) and Task 3 (worker) get a full spec + code-quality review; Tasks 2, 4, 5 spec-check + quality-check; Tasks 6–8 spec-check. After Task 8: whole-branch review, then PR `feature/p1b-live-scores` → `main`, watch CI, squash-merge.
