# P1a — Team Linking & Dashboard Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Enter an FPL manager (entry) ID → the platform fetches and stores that team's squad picks, chips, and per-gameweek history, and the Next.js dashboard shows the squad with each player's xP plus a rank/points history view.

**Architecture:** New `linked_teams` / `entry_gw_history` / `entry_picks` tables; three `FplClient` methods + three pure normalizers for `entry/{id}/`, `entry/{id}/history/`, `entry/{id}/event/{gw}/picks/`; a `sync_entry(entry_id)` worker task (+ a Beat task that re-syncs all linked teams); read API `POST /link/{entry_id}`, `GET /entries/{id}`, `GET /entries/{id}/history`; a dashboard nav shell + "link team" form (entry id kept in `localStorage`) + squad page joining picks → players → `player_gw_predictions`.

**No auth in this sub-plan.** Everything is keyed on the public FPL entry ID. Accounts (email/password or Google OAuth) are a later sub-plan **P1a-auth** — blocked on the OAuth-credentials / email-transport decision.

**Tech Stack:** unchanged from Foundation/P1c — Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, Celery, httpx, Next.js 16 + Vitest. `venv`+`pip`, `python -m <tool>`, commits staged `git add -A -- ':!docs'`, author `Anil Kujur <anilkuj@gmail.com>` + `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`. Branch: `feature/p1a-team-dashboard` off `main`.

**Reference:** master plan §3 P1a, PRD §4.1 / §4.8.

---

## Context from Foundation + P1c (built)

- `fplguru_core.models`: `Team`, `Gameweek` (`is_current`, `is_next`, `finished`, `deadline_time`), `Player` (`id`, `web_name`, `position`, `now_cost`, `team_id`), `Fixture`, `DataSyncLog`, `PlayerGwStat`, `PlayerGwFeature`, `PlayerGwPrediction` (`player_id`, `gameweek_id`, `horizon_gw`, `model_version`, `xp`, `xp_floor`, `xp_ceiling`). `Base.metadata` has a `naming_convention`. `_TimestampMixin` gives `updated_at`.
- `fplguru_core.db`: `get_sessionmaker()`, `session_scope()`, `dispose_engine()`, `reset_state()`.
- `fplguru_fpl_client.FplClient`: async, `_get(path)`, `bootstrap_static()`, `fixtures()`, `event_live(gw)`. Add `entry`, `entry_history`, `entry_picks` here.
- `fplguru_ingest.fpl`: `normalize_teams/gameweeks/players/fixtures/event_live`, `_parse_dt`.
- `services/worker/tasks.py`: `_upsert(session, model, rows) -> int` (keys on `id`), `_upsert_stats` (keys on a composite), `_record`, `_log_error`, `_run_and_dispose(coro_fn)`, Celery tasks + Beat schedule (`sync-bootstrap`, `sync-fixtures`, `sync-gw-stats`, `compute-xp`). `_upsert_predictions` in `xp.py` shows the composite-key upsert pattern.
- `services/api/main.py`: `get_db` (read-only), `_gw`, `_MODEL_VERSION = "basic-v1"`, endpoints `/health /ready /gameweeks /gameweeks/current /status /xp /players/{id}/xp`. `/status` enumerates `distinct(DataSyncLog.source) | {fpl_bootstrap, fpl_fixtures}`.
- Root `conftest.py`: `db_engine` (session, opt-in), `db_session` (function, truncate-after), autouse `_point_app_at_test_db`. **FK-parent-first seeding** — models have no `relationship()`, so a single `add_all` of parents+children flushes alphabetically and violates FKs. Seed & `commit()` in waves.
- `apps/web`: Next 16 App Router, Tailwind v4, Vitest 4. `src/lib/api.ts` has `fetchStatus`. `src/app/page.tsx` reads `/status`. `NEXT_PUBLIC_API_BASE` env (default `http://localhost:8000`).
- `ruff` runs locally (`python -m ruff check .`) and in CI; `select = ["E","F","I","UP","B"]`, line-length 100, `[tool.ruff.lint.isort] known-first-party` set, `alembic/*` E402/E501/I001/UP035/UP007-exempt.

---

## FPL API shapes (verified against `entry/1/`)

- `GET entry/{id}/` → `{id, name, player_first_name, player_last_name, started_event, favourite_team, summary_overall_points, summary_overall_rank, ...}`
- `GET entry/{id}/history/` → `{current: [{event, points, total_points, rank, overall_rank, bank, value, event_transfers, event_transfers_cost, points_on_bench}], past: [...], chips: [{name, event}]}`
- `GET entry/{id}/event/{gw}/picks/` → `{active_chip, automatic_subs, entry_history, picks: [{element, position, multiplier, is_captain, is_vice_captain, element_type}]}`. Returns 404 before a manager has a squad for that GW.

---

## File structure

| Path | Responsibility |
|---|---|
| `packages/core/.../models.py` (modify) | `LinkedTeam`, `EntryGwHistory`, `EntryPick` |
| `alembic/versions/0003_*.py` | migration for the 3 tables |
| `packages/fpl_client/.../client.py` (modify) | `entry(id)`, `entry_history(id)`, `entry_picks(id, gw)` |
| `packages/ingest/.../fpl.py` (modify) | `normalize_entry`, `normalize_entry_history`, `normalize_entry_picks` |
| `services/worker/.../entries.py` (new) | `sync_entry(entry_id)` core coroutine |
| `services/worker/.../tasks.py` (modify) | `sync_entry` + `sync_linked_teams` Celery tasks + Beat |
| `services/api/.../main.py` (modify) | `POST /link/{entry_id}`, `GET /entries/{id}`, `GET /entries/{id}/history` |
| `apps/web/src/lib/api.ts` (modify) | `linkEntry`, `getEntry`, `getEntryHistory` typed clients |
| `apps/web/src/app/layout.tsx` (modify) | nav shell (Squad · xP · FDR · Live) |
| `apps/web/src/app/page.tsx` (modify) | "link your team" form → `localStorage` → redirect to `/squad` |
| `apps/web/src/app/squad/page.tsx` (new) | squad table: picks → players → xP column |
| `apps/web/src/lib/entry.ts` (new) | `getStoredEntryId()` / `setStoredEntryId()` (localStorage, guarded) |

---

## Task 1: models + `0003` migration

**Files:** modify `packages/core/src/fplguru_core/models.py`; create `packages/core/tests/test_entry_models.py`; create `alembic/versions/0003_entry_tables.py`.

- [ ] **Step 1: failing test** — `packages/core/tests/test_entry_models.py`:
```python
from fplguru_core.models import Base, EntryGwHistory, EntryPick, LinkedTeam


def test_entry_tables_registered():
    assert {"linked_teams", "entry_gw_history", "entry_picks"} <= set(Base.metadata.tables)


def test_linked_team_unique_on_entry_id():
    uqs = [c for c in LinkedTeam.__table__.constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert any({"fpl_entry_id"} == {c.name for c in uq.columns} for uq in uqs)


def test_pick_columns():
    cols = {c.name for c in EntryPick.__table__.columns}
    assert {"linked_team_id", "gameweek_id", "player_id", "slot", "multiplier",
            "is_captain", "is_vice"} <= cols


def test_history_columns():
    cols = {c.name for c in EntryGwHistory.__table__.columns}
    assert {"linked_team_id", "gameweek_id", "points", "total_points", "overall_rank",
            "bank", "team_value", "transfers", "transfer_cost", "points_on_bench"} <= cols
```

- [ ] **Step 2: run → fails.**

- [ ] **Step 3: add to `models.py`** (append after `PlayerGwPrediction`; extend the sqlalchemy import for `UniqueConstraint` if not already there — it is, from P1c):
```python
class LinkedTeam(_TimestampMixin, Base):
    __tablename__ = "linked_teams"
    __table_args__ = (UniqueConstraint("fpl_entry_id", name="uq_linked_teams_fpl_entry_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fpl_entry_id: Mapped[int] = mapped_column(Integer, index=True)
    manager_name: Mapped[str] = mapped_column(String(128), default="")
    started_event: Mapped[int | None] = mapped_column(Integer, nullable=True)
    favourite_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EntryGwHistory(_TimestampMixin, Base):
    __tablename__ = "entry_gw_history"
    __table_args__ = (UniqueConstraint("linked_team_id", "gameweek_id",
                                       name="uq_entry_gw_history_linked_team_id_gameweek_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    linked_team_id: Mapped[int] = mapped_column(ForeignKey("linked_teams.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    overall_rank: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bank: Mapped[int] = mapped_column(Integer, default=0)          # tenths
    team_value: Mapped[int] = mapped_column(Integer, default=0)    # tenths
    transfers: Mapped[int] = mapped_column(Integer, default=0)
    transfer_cost: Mapped[int] = mapped_column(Integer, default=0)
    points_on_bench: Mapped[int] = mapped_column(Integer, default=0)


class EntryPick(_TimestampMixin, Base):
    __tablename__ = "entry_picks"
    __table_args__ = (UniqueConstraint("linked_team_id", "gameweek_id", "player_id",
                                       name="uq_entry_picks_linked_team_id_gameweek_id_player_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    linked_team_id: Mapped[int] = mapped_column(ForeignKey("linked_teams.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    slot: Mapped[int] = mapped_column(Integer)              # 1..15 (FPL "position")
    multiplier: Mapped[int] = mapped_column(Integer, default=1)
    is_captain: Mapped[bool] = mapped_column(Boolean, default=False)
    is_vice: Mapped[bool] = mapped_column(Boolean, default=False)
```

- [ ] **Step 4: run → 4 passed.**

- [ ] **Step 5: migration** — `docker compose -f infra/docker-compose.yml up -d --wait`, then `python -m alembic revision --autogenerate -m "entry tables" --rev-id 0003`, `python -m alembic upgrade head`, `python -m alembic check`. Confirm 3 `create_table`, `down_revision = "0002"`, convention names, no alters to existing tables.

- [ ] **Step 6:** `python -m pytest -q` → all green (+4). `python -m ruff check .` → clean.

- [ ] **Step 7: commit** `feat(core): linked_teams / entry_gw_history / entry_picks + 0003 migration`

---

## Task 2: `FplClient` entry methods

**Files:** modify `client.py`; append to `packages/fpl_client/tests/test_client.py`.

- [ ] **Step 1: tests** (append):
```python
@respx.mock
async def test_entry_and_history_and_picks():
    respx.get(f"{BASE}/entry/7/").mock(return_value=httpx.Response(200, json={"id": 7, "name": "T"}))
    respx.get(f"{BASE}/entry/7/history/").mock(return_value=httpx.Response(200, json={"current": []}))
    respx.get(f"{BASE}/entry/7/event/3/picks/").mock(
        return_value=httpx.Response(200, json={"picks": [], "active_chip": None}))
    async with FplClient(BASE) as c:
        assert (await c.entry(7))["id"] == 7
        assert "current" in await c.entry_history(7)
        assert "picks" in await c.entry_picks(7, 3)
```

- [ ] **Step 2: add to `client.py`** (after `event_live`):
```python
    async def entry(self, entry_id: int) -> dict:
        return await self._get(f"entry/{entry_id}/")

    async def entry_history(self, entry_id: int) -> dict:
        return await self._get(f"entry/{entry_id}/history/")

    async def entry_picks(self, entry_id: int, gameweek: int) -> dict:
        return await self._get(f"entry/{entry_id}/event/{gameweek}/picks/")
```

- [ ] **Step 3:** run fpl_client tests → green. Full `pytest -q`, `ruff` → clean. Commit `feat(fpl-client): entry / entry_history / entry_picks`.

---

## Task 3: entry normalizers

**Files:** modify `packages/ingest/src/fplguru_ingest/fpl.py`; create `packages/ingest/tests/fixtures/entry_sample.json`, `entry_history_sample.json`, `entry_picks_sample.json`; append to `test_fpl_normalizers.py`.

- [ ] **Step 1: fixtures**

`entry_sample.json`:
```json
{"id": 7, "name": "My Team", "player_first_name": "Sam", "player_last_name": "Q",
 "started_event": 1, "favourite_team": 3}
```
`entry_history_sample.json`:
```json
{"current": [
  {"event": 1, "points": 55, "total_points": 55, "rank": 100, "overall_rank": 250000,
   "bank": 5, "value": 1000, "event_transfers": 0, "event_transfers_cost": 0, "points_on_bench": 8},
  {"event": 2, "points": 60, "total_points": 115, "rank": 90, "overall_rank": 180000,
   "bank": 2, "value": 1003, "event_transfers": 1, "event_transfers_cost": 4, "points_on_bench": 5}
], "past": [], "chips": []}
```
`entry_picks_sample.json`:
```json
{"active_chip": null, "automatic_subs": [], "entry_history": {},
 "picks": [
   {"element": 11, "position": 1, "multiplier": 1, "is_captain": false, "is_vice_captain": false, "element_type": 1},
   {"element": 12, "position": 12, "multiplier": 2, "is_captain": true, "is_vice_captain": false, "element_type": 3}
]}
```

- [ ] **Step 2: tests** (append; add the 3 names to the `from fplguru_ingest.fpl import (...)` line):
```python
ENTRY = json.loads((FIX / "entry_sample.json").read_text())
ENTRY_HISTORY = json.loads((FIX / "entry_history_sample.json").read_text())
ENTRY_PICKS = json.loads((FIX / "entry_picks_sample.json").read_text())


def test_normalize_entry():
    assert normalize_entry(ENTRY) == {
        "fpl_entry_id": 7, "manager_name": "Sam Q", "started_event": 1, "favourite_team_id": 3,
    }


def test_normalize_entry_history_maps_current():
    rows = normalize_entry_history(ENTRY_HISTORY)
    assert rows[0] == {
        "gameweek_id": 1, "points": 55, "total_points": 55, "overall_rank": 250000,
        "bank": 5, "team_value": 1000, "transfers": 0, "transfer_cost": 0, "points_on_bench": 8,
    }
    assert rows[1]["transfer_cost"] == 4


def test_normalize_entry_picks():
    rows = normalize_entry_picks(3, ENTRY_PICKS)
    assert rows[0] == {
        "gameweek_id": 3, "player_id": 11, "slot": 1, "multiplier": 1,
        "is_captain": False, "is_vice": False,
    }
    assert rows[1]["is_captain"] is True and rows[1]["multiplier"] == 2
```

- [ ] **Step 3: implement** in `fpl.py`:
```python
def normalize_entry(payload: dict[str, Any]) -> dict:
    first = payload.get("player_first_name", "")
    last = payload.get("player_last_name", "")
    return {
        "fpl_entry_id": payload["id"],
        "manager_name": f"{first} {last}".strip(),
        "started_event": payload.get("started_event"),
        "favourite_team_id": payload.get("favourite_team"),
    }


def normalize_entry_history(payload: dict[str, Any]) -> list[dict]:
    return [
        {
            "gameweek_id": r["event"],
            "points": r["points"],
            "total_points": r["total_points"],
            "overall_rank": r.get("overall_rank"),
            "bank": r["bank"],
            "team_value": r["value"],
            "transfers": r["event_transfers"],
            "transfer_cost": r["event_transfers_cost"],
            "points_on_bench": r["points_on_bench"],
        }
        for r in payload.get("current", [])
    ]


def normalize_entry_picks(gameweek_id: int, payload: dict[str, Any]) -> list[dict]:
    return [
        {
            "gameweek_id": gameweek_id,
            "player_id": p["element"],
            "slot": p["position"],
            "multiplier": p["multiplier"],
            "is_captain": bool(p["is_captain"]),
            "is_vice": bool(p["is_vice_captain"]),
        }
        for p in payload.get("picks", [])
    ]
```

- [ ] **Step 4:** run → green. `pytest -q` + `ruff` clean. Commit `feat(ingest): entry / entry_history / entry_picks normalizers`.

---

## Task 4: `sync_entry` worker

**Files:** create `services/worker/src/fplguru_worker/entries.py`; modify `tasks.py`, `app.py`, `test_beat_schedule.py`; create `services/worker/tests/test_sync_entry.py`.

- [ ] **Step 1: failing test** — `services/worker/tests/test_sync_entry.py`:
```python
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx
from sqlalchemy import select

from fplguru_core.models import EntryGwHistory, EntryPick, Gameweek, LinkedTeam, Player, Team
from fplguru_worker.entries import sync_entry

FIX = Path(__file__).parents[3] / "packages/ingest/tests/fixtures"
ENTRY = json.loads((FIX / "entry_sample.json").read_text())
HIST = json.loads((FIX / "entry_history_sample.json").read_text())
PICKS = json.loads((FIX / "entry_picks_sample.json").read_text())
BASE = "https://fpl.test/api"


async def test_sync_entry_creates_link_history_and_picks(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    db_session.add_all([Team(id=3, name="C", short_name="C")])
    db_session.add_all([
        Gameweek(id=1, name="GW1", deadline_time=datetime(2025, 8, 1, tzinfo=UTC), finished=True),
        Gameweek(id=2, name="GW2", deadline_time=datetime(2025, 8, 8, tzinfo=UTC), finished=True),
    ])
    await db_session.commit()
    db_session.add_all([
        Player(id=11, team_id=3, first_name="a", second_name="b", web_name="ab", position="GK",
               now_cost=45, status="a", selected_by_percent=1.0, total_points=0),
        Player(id=12, team_id=3, first_name="c", second_name="d", web_name="cd", position="MID",
               now_cost=80, status="a", selected_by_percent=1.0, total_points=0),
    ])
    await db_session.commit()
    respx.get(f"{BASE}/entry/7/").mock(return_value=httpx.Response(200, json=ENTRY))
    respx.get(f"{BASE}/entry/7/history/").mock(return_value=httpx.Response(200, json=HIST))
    respx.get(f"{BASE}/entry/7/event/2/picks/").mock(return_value=httpx.Response(200, json=PICKS))

    lt_id = await sync_entry(7)

    lt = (await db_session.execute(select(LinkedTeam).where(LinkedTeam.id == lt_id))).scalar_one()
    assert lt.fpl_entry_id == 7 and lt.manager_name == "Sam Q"
    hist = (await db_session.execute(
        select(EntryGwHistory).where(EntryGwHistory.linked_team_id == lt_id)
    )).scalars().all()
    assert {h.gameweek_id for h in hist} == {1, 2}
    picks = (await db_session.execute(
        select(EntryPick).where(EntryPick.linked_team_id == lt_id)
    )).scalars().all()
    assert {p.player_id for p in picks} == {11, 12} and any(p.is_captain for p in picks)


@respx.mock
async def test_sync_entry_is_idempotent(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    db_session.add_all([Team(id=3, name="C", short_name="C")])
    db_session.add(Gameweek(id=2, name="GW2", deadline_time=datetime(2025, 8, 8, tzinfo=UTC),
                            finished=True))
    await db_session.commit()
    db_session.add(Player(id=11, team_id=3, first_name="a", second_name="b", web_name="ab",
                          position="GK", now_cost=45, status="a", selected_by_percent=1.0,
                          total_points=0))
    db_session.add(Player(id=12, team_id=3, first_name="c", second_name="d", web_name="cd",
                          position="MID", now_cost=80, status="a", selected_by_percent=1.0,
                          total_points=0))
    await db_session.commit()
    respx.get(f"{BASE}/entry/7/").mock(return_value=httpx.Response(200, json=ENTRY))
    respx.get(f"{BASE}/entry/7/history/").mock(
        return_value=httpx.Response(200, json={"current": [HIST["current"][1]]}))
    respx.get(f"{BASE}/entry/7/event/2/picks/").mock(return_value=httpx.Response(200, json=PICKS))

    a = await sync_entry(7)
    b = await sync_entry(7)
    assert a == b
    from sqlalchemy import func
    n = (await db_session.execute(
        select(func.count()).select_from(EntryPick).where(EntryPick.linked_team_id == a)
    )).scalar()
    assert n == 2
```
> `@respx.mock` on the first test is provided by the decorator on the module? add `@respx.mock` to `test_sync_entry_creates_...` too.

- [ ] **Step 2: implement `entries.py`**:
```python
"""Fetch one FPL entry (manager) and upsert its link row, GW history and latest picks."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from fplguru_core.db import get_sessionmaker
from fplguru_core.models import DataSyncLog, EntryGwHistory, EntryPick, Gameweek, LinkedTeam
from fplguru_core.settings import get_settings
from fplguru_fpl_client import FplClient
from fplguru_ingest.fpl import normalize_entry, normalize_entry_history, normalize_entry_picks

logger = logging.getLogger("fplguru.worker")


async def _upsert(session, model, rows, keys):
    if not rows:
        return
    stmt = pg_insert(model).values(rows)
    update = {c: stmt.excluded[c] for c in rows[0] if c not in keys}
    update["updated_at"] = func.now()
    await session.execute(
        stmt.on_conflict_do_update(index_elements=list(keys), set_=update)
    )


async def sync_entry(entry_id: int) -> int:
    started = datetime.now(UTC)
    client = FplClient(get_settings().fpl_api_base)
    try:
        profile = await client.entry(entry_id)
        history = await client.entry_history(entry_id)
        latest_finished = None
        async with get_sessionmaker()() as session:
            latest_finished = (await session.execute(
                select(func.max(Gameweek.id)).where(Gameweek.finished.is_(True))
            )).scalar()
        picks = (
            await client.entry_picks(entry_id, latest_finished) if latest_finished else {"picks": []}
        )
    finally:
        await client.aclose()

    ent = normalize_entry(profile)
    async with get_sessionmaker()() as session, session.begin():
        lt = (await session.execute(
            select(LinkedTeam).where(LinkedTeam.fpl_entry_id == entry_id)
        )).scalar_one_or_none()
        if lt is None:
            lt = LinkedTeam(**ent, last_synced_at=datetime.now(UTC))
            session.add(lt)
            await session.flush()
        else:
            lt.manager_name = ent["manager_name"]
            lt.started_event = ent["started_event"]
            lt.favourite_team_id = ent["favourite_team_id"]
            lt.last_synced_at = datetime.now(UTC)
        lt_id = lt.id

        hist_rows = [
            {"linked_team_id": lt_id, **r} for r in normalize_entry_history(history)
        ]
        await _upsert(session, EntryGwHistory, hist_rows,
                      keys=("linked_team_id", "gameweek_id"))

        if latest_finished:
            pick_rows = [
                {"linked_team_id": lt_id, **r}
                for r in normalize_entry_picks(latest_finished, picks)
            ]
            await _upsert(session, EntryPick, pick_rows,
                          keys=("linked_team_id", "gameweek_id", "player_id"))

        session.add(DataSyncLog(source="fpl_entry", status="ok",
                                detail=f"entry {entry_id}: {len(hist_rows)} gw, {len(picks.get('picks', []))} picks",
                                started_at=started, finished_at=datetime.now(UTC)))
    logger.info("synced entry %s -> linked_team %s", entry_id, lt_id)
    return lt_id
```

- [ ] **Step 3: `tasks.py`** — add:
```python
from fplguru_worker.entries import sync_entry


@celery_app.task(name="sync_entry", bind=True, max_retries=3, default_retry_delay=60)
def sync_entry_task(self, entry_id: int) -> None:
    try:
        asyncio.run(_run_and_dispose(lambda: sync_entry(entry_id)))
    except Exception as exc:
        raise self.retry(exc=exc) from exc


async def _sync_linked_teams() -> None:
    async with get_sessionmaker()() as session:
        ids = (await session.execute(select(LinkedTeam.fpl_entry_id))).scalars().all()
    for eid in ids:
        await sync_entry(eid)


@celery_app.task(name="sync_linked_teams", bind=True, max_retries=2, default_retry_delay=120)
def sync_linked_teams(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_sync_linked_teams))
    except Exception as exc:
        raise self.retry(exc=exc) from exc
```
Add `from fplguru_core.models import LinkedTeam` to the models import. `app.py` beat: `"sync-linked-teams": {"task": "sync_linked_teams", "schedule": 3600.0}`. `test_beat_schedule.py`: assert it.

- [ ] **Step 4:** run worker tests → green. `pytest -q` + `ruff` clean. Commit `feat(worker): sync_entry — link + history + picks`.

---

## Task 5: API — link + read endpoints

**Files:** modify `services/api/src/fplguru_api/main.py`; create `services/api/tests/test_entries_api.py`.

- [ ] **Step 1: failing test** — `services/api/tests/test_entries_api.py`:
```python
from datetime import UTC, datetime

import httpx
import respx
from fplguru_core.models import (EntryGwHistory, EntryPick, Gameweek, LinkedTeam, Player,
                                 PlayerGwPrediction, Team)

BASE = "https://fpl.test/api"


async def _seed(db_session):
    db_session.add(Team(id=3, name="C", short_name="C"))
    db_session.add_all([
        Gameweek(id=1, name="GW1", deadline_time=datetime(2025, 8, 1, tzinfo=UTC), finished=True),
        Gameweek(id=2, name="GW2", deadline_time=datetime(2025, 8, 8, tzinfo=UTC), is_next=True),
    ])
    await db_session.commit()
    db_session.add(Player(id=12, team_id=3, first_name="c", second_name="d", web_name="Cap",
                          position="MID", now_cost=80, status="a", selected_by_percent=1.0,
                          total_points=0))
    await db_session.commit()
    lt = LinkedTeam(fpl_entry_id=7, manager_name="Sam Q", started_event=1)
    db_session.add(lt)
    await db_session.commit()
    db_session.add(EntryGwHistory(linked_team_id=lt.id, gameweek_id=1, points=55, total_points=55,
                                  overall_rank=1000, bank=5, team_value=1000, transfers=0,
                                  transfer_cost=0, points_on_bench=8))
    db_session.add(EntryPick(linked_team_id=lt.id, gameweek_id=1, player_id=12, slot=12,
                             multiplier=2, is_captain=True, is_vice=False))
    db_session.add(PlayerGwPrediction(player_id=12, gameweek_id=2, horizon_gw=1,
                                      model_version="basic-v1", xp=5.5, xp_floor=3, xp_ceiling=8))
    await db_session.commit()
    return lt.id


@respx.mock
async def test_link_creates_and_returns_entry(client, db_session):
    import json
    from pathlib import Path
    fix = Path(__file__).parents[3] / "packages/ingest/tests/fixtures"
    respx.get(f"{BASE}/entry/7/").mock(return_value=httpx.Response(
        200, json=json.loads((fix / "entry_sample.json").read_text())))
    respx.get(f"{BASE}/entry/7/history/").mock(return_value=httpx.Response(
        200, json=json.loads((fix / "entry_history_sample.json").read_text())))
    db_session.add(Gameweek(id=1, name="GW1", deadline_time=datetime(2025, 8, 1, tzinfo=UTC),
                            finished=True))
    db_session.add(Team(id=3, name="C", short_name="C"))
    await db_session.commit()
    db_session.add(Player(id=11, team_id=3, first_name="a", second_name="b", web_name="ab",
                          position="GK", now_cost=45, status="a", selected_by_percent=1.0,
                          total_points=0))
    db_session.add(Player(id=12, team_id=3, first_name="c", second_name="d", web_name="cd",
                          position="MID", now_cost=80, status="a", selected_by_percent=1.0,
                          total_points=0))
    await db_session.commit()
    respx.get(f"{BASE}/entry/7/event/1/picks/").mock(return_value=httpx.Response(
        200, json=json.loads((fix / "entry_picks_sample.json").read_text())))
    monkeypatch_env(client)  # see note below

    r = await client.post("/link/7")
    assert r.status_code == 200
    assert r.json()["fpl_entry_id"] == 7


async def test_get_entry_squad_with_xp(client, db_session):
    await _seed(db_session)
    r = await client.get("/entries/7")
    body = r.json()
    assert body["manager_name"] == "Sam Q"
    cap = next(p for p in body["picks"] if p["is_captain"])
    assert cap["web_name"] == "Cap" and abs(cap["xp"] - 5.5) < 1e-6


async def test_get_entry_history(client, db_session):
    await _seed(db_session)
    r = await client.get("/entries/7/history")
    rows = r.json()
    assert rows[0]["gameweek_id"] == 1 and rows[0]["total_points"] == 55


async def test_get_unknown_entry_404(client):
    r = await client.get("/entries/999")
    assert r.status_code == 404
```
> The `test_link_*` test needs `FPLGURU_FPL_API_BASE` pointed at `BASE` for the app's `sync_entry` call. Add a small helper: at the top of the test, `import os; os.environ["FPLGURU_FPL_API_BASE"] = BASE` won't undo — instead pass a `monkeypatch` fixture into the test and `monkeypatch.setenv(...)`. Rework `test_link_creates_and_returns_entry(client, db_session, monkeypatch)` and drop the `monkeypatch_env(client)` line; call `monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)` first.

- [ ] **Step 2: implement in `main.py`** — extend imports (`EntryGwHistory, EntryPick, LinkedTeam` from models; `from fplguru_worker.entries import sync_entry`? **NO** — api must not import worker). Instead the API calls a thin inline version, or better: move `sync_entry` to a **shared** location. Simplest for P1a: `POST /link/{entry_id}` does the fetch+upsert *inline* by importing from `fplguru_ingest` + `fplguru_fpl_client` directly (same code path, no `services/worker` dep). Extract the entry-sync coroutine into `packages/ingest`? It touches the DB, which `packages/ingest` must not. **Resolution:** put the shared entry-sync coroutine in a new tiny package-neutral spot — `fplguru_core`? no. Pragmatic call: **duplicate the ~15-line upsert in the API endpoint** (it's small and read-mostly), OR make `services/api` depend on `services/worker`. Prefer: `services/api` `pip` dependency on `fplguru-worker` is heavy (pulls celery). **Chosen:** add `fplguru-worker` to `services/api` deps is wrong. Instead, in Task 4, put `sync_entry` in `packages/ingest`... no (DB).
>
> **Final decision:** create `packages/entrysync` — a tiny package with just `sync_entry(entry_id)` depending on `fplguru-core` + `fplguru-fpl-client` + `fplguru-ingest`. Both `services/worker` and `services/api` depend on it. Update Task 4 to create `packages/entrysync/src/fplguru_entrysync/__init__.py` with `sync_entry`, and `services/worker/entries.py` becomes a 1-line re-export. This keeps the api free of celery. **Do Task 4 that way.**

```python
from fplguru_entrysync import sync_entry
from fplguru_core.models import EntryGwHistory, EntryPick, LinkedTeam


@app.post("/link/{entry_id}")
async def link_entry(entry_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await sync_entry(entry_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"could not sync entry {entry_id}") from exc
    lt = (await db.execute(
        select(LinkedTeam).where(LinkedTeam.fpl_entry_id == entry_id)
    )).scalar_one()
    return {"fpl_entry_id": lt.fpl_entry_id, "manager_name": lt.manager_name,
            "linked_team_id": lt.id}


async def _entry_or_404(db, entry_id: int) -> LinkedTeam:
    lt = (await db.execute(
        select(LinkedTeam).where(LinkedTeam.fpl_entry_id == entry_id)
    )).scalar_one_or_none()
    if lt is None:
        raise HTTPException(status_code=404, detail="entry not linked")
    return lt


@app.get("/entries/{entry_id}")
async def get_entry(entry_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    lt = await _entry_or_404(db, entry_id)
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
        pids = [p.id for _, p in rows]
        for pid, total in (await db.execute(
            select(PlayerGwPrediction.player_id, func.sum(PlayerGwPrediction.xp))
            .where(PlayerGwPrediction.player_id.in_(pids),
                   PlayerGwPrediction.model_version == _MODEL_VERSION)
            .group_by(PlayerGwPrediction.player_id)
        )).all():
            xp_by_player[pid] = float(total)
    return {
        "fpl_entry_id": lt.fpl_entry_id, "manager_name": lt.manager_name,
        "last_synced_at": lt.last_synced_at.isoformat() if lt.last_synced_at else None,
        "picks_gameweek_id": latest_pick_gw,
        "picks": [
            {"slot": ep.slot, "player_id": pl.id, "web_name": pl.web_name,
             "position": pl.position, "now_cost": pl.now_cost,
             "multiplier": ep.multiplier, "is_captain": ep.is_captain, "is_vice": ep.is_vice,
             "xp": xp_by_player.get(pl.id, 0.0)}
            for ep, pl in rows
        ],
    }


@app.get("/entries/{entry_id}/history")
async def get_entry_history(entry_id: int, db: AsyncSession = Depends(get_db)) -> list[dict]:
    lt = await _entry_or_404(db, entry_id)
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
```
Add `func` to the sqlalchemy import in `main.py` if not present.

- [ ] **Step 3:** `services/api/pyproject.toml` — add `"fplguru-entrysync"` to deps. `pip install -r requirements-dev.txt`.

- [ ] **Step 4:** run api tests → green. `pytest -q` + `ruff` + `alembic check` clean. Commit `feat(api): POST /link/{id}, GET /entries/{id}, GET /entries/{id}/history`.

---

## Task 6: `packages/entrysync` extraction (do BEFORE Task 4/5 wire-up if not already)

**Files:** create `packages/entrysync/pyproject.toml`, `src/fplguru_entrysync/__init__.py`; add `-e ./packages/entrysync` to root `requirements-dev.txt`; make `services/worker/entries.py` re-export.

> If Task 4 already put `sync_entry` in `packages/entrysync`, this task is just the `pyproject.toml` + `requirements-dev.txt` bookkeeping and can be folded into Task 4. Keeping it listed so the dependency wiring isn't forgotten. `packages/entrysync` deps: `fplguru-core`, `fplguru-fpl-client`, `fplguru-ingest`.

- [ ] Steps: create the package skeleton; move `sync_entry` there; `services/worker/src/fplguru_worker/entries.py` = `from fplguru_entrysync import sync_entry  # noqa: F401`; `services/worker/pyproject.toml` deps add `fplguru-entrysync`; `pip install -r requirements-dev.txt`; `pytest -q` green; commit `refactor: extract fplguru-entrysync (shared by api + worker)`.

---

## Task 7: web — typed API client + entry storage

**Files:** modify `apps/web/src/lib/api.ts`; create `apps/web/src/lib/entry.ts`; create `apps/web/src/lib/api.entries.test.ts`.

- [ ] **Step 1: failing test** — `apps/web/src/lib/api.entries.test.ts`:
```ts
import { describe, expect, it, vi } from "vitest";
import { getEntry, linkEntry } from "./api";

describe("entries api", () => {
  it("linkEntry POSTs and returns body", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ fpl_entry_id: 7, manager_name: "Sam Q" }),
    }) as unknown as typeof fetch;
    const r = await linkEntry("http://api.test", 7);
    expect(r.fpl_entry_id).toBe(7);
  });

  it("getEntry throws on !ok", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 }) as unknown as typeof fetch;
    await expect(getEntry("http://api.test", 7)).rejects.toThrow();
  });
});
```

- [ ] **Step 2: implement** in `api.ts` (append):
```ts
export type EntryPick = {
  slot: number; player_id: number; web_name: string; position: string;
  now_cost: number; multiplier: number; is_captain: boolean; is_vice: boolean; xp: number;
};
export type Entry = {
  fpl_entry_id: number; manager_name: string; last_synced_at: string | null;
  picks_gameweek_id: number | null; picks: EntryPick[];
};
export type EntryHistoryRow = {
  gameweek_id: number; points: number; total_points: number; overall_rank: number | null;
  bank: number; team_value: number; transfers: number; transfer_cost: number; points_on_bench: number;
};

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`http ${res.status}`);
  return (await res.json()) as T;
}

export const linkEntry = (base: string, id: number) =>
  fetch(`${base}/link/${id}`, { method: "POST" }).then(j<{ fpl_entry_id: number; manager_name: string }>);
export const getEntry = (base: string, id: number) =>
  fetch(`${base}/entries/${id}`, { cache: "no-store" }).then(j<Entry>);
export const getEntryHistory = (base: string, id: number) =>
  fetch(`${base}/entries/${id}/history`, { cache: "no-store" }).then(j<EntryHistoryRow[]>);
```

- [ ] **Step 3: `apps/web/src/lib/entry.ts`**:
```ts
const KEY = "fplguru.entryId";

export function getStoredEntryId(): number | null {
  try {
    const v = typeof window !== "undefined" ? window.localStorage.getItem(KEY) : null;
    return v ? Number(v) : null;
  } catch {
    return null;
  }
}

export function setStoredEntryId(id: number): void {
  try {
    window.localStorage.setItem(KEY, String(id));
  } catch {
    /* private mode / no storage — ignore */
  }
}
```

- [ ] **Step 4:** `pnpm --filter web test` → green. Commit `feat(web): typed entry API client + localStorage entry id`.

---

## Task 8: web — nav shell + link form + squad page

**Files:** modify `apps/web/src/app/layout.tsx`, `apps/web/src/app/page.tsx`; create `apps/web/src/app/squad/page.tsx`; create `apps/web/src/app/squad/SquadTable.tsx` (client component).

- [ ] **Step 1: nav in `layout.tsx`** — inside `<body>`, above `{children}`, add a simple nav:
```tsx
<nav className="border-b px-6 py-3 text-sm flex gap-4">
  <a href="/" className="font-semibold">FPLGuru</a>
  <a href="/squad">Squad</a>
  <span className="text-gray-400">xP</span>
  <span className="text-gray-400">FDR</span>
  <span className="text-gray-400">Live</span>
</nav>
```
(the greyed spans are placeholders for P1d / P1b.)

- [ ] **Step 2: `page.tsx`** — replace the body with a client "link your team" form:
```tsx
"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { linkEntry } from "@/lib/api";
import { setStoredEntryId } from "@/lib/entry";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export default function Home() {
  const [id, setId] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const n = Number(id);
      if (!Number.isInteger(n) || n <= 0) throw new Error("Enter a numeric FPL team ID");
      await linkEntry(API, n);
      setStoredEntryId(n);
      router.push("/squad");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to link");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="p-8 max-w-md">
      <h1 className="text-2xl font-semibold">Link your FPL team</h1>
      <p className="mt-1 text-sm text-gray-500">
        Your team ID is in the URL on the FPL &ldquo;Points&rdquo; page:
        <code className="mx-1">/entry/&lt;ID&gt;/event/…</code>
      </p>
      <form onSubmit={submit} className="mt-4 flex gap-2">
        <input
          value={id}
          onChange={(e) => setId(e.target.value)}
          inputMode="numeric"
          placeholder="e.g. 1234567"
          className="border rounded px-3 py-2 flex-1"
        />
        <button disabled={busy} className="border rounded px-4 py-2 disabled:opacity-50">
          {busy ? "…" : "Link"}
        </button>
      </form>
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
    </main>
  );
}
```

- [ ] **Step 3: `squad/page.tsx`** (server component that just renders the client table):
```tsx
import { SquadTable } from "./SquadTable";

export default function SquadPage() {
  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">Squad</h1>
      <SquadTable />
    </main>
  );
}
```
`squad/SquadTable.tsx`:
```tsx
"use client";
import { useEffect, useState } from "react";
import { getEntry, type Entry } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function SquadTable() {
  const [entry, setEntry] = useState<Entry | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const id = getStoredEntryId();
    if (!id) {
      setErr("No team linked yet — go to the home page.");
      return;
    }
    getEntry(API, id).then(setEntry).catch(() => setErr("Could not load squad."));
  }, []);

  if (err) return <p className="mt-4 text-sm text-gray-500">{err}</p>;
  if (!entry) return <p className="mt-4 text-sm text-gray-400">Loading…</p>;

  return (
    <>
      <p className="mt-1 text-sm text-gray-500">
        {entry.manager_name} · picks from GW {entry.picks_gameweek_id ?? "—"}
      </p>
      <table className="mt-4 w-full text-sm">
        <thead>
          <tr className="text-left border-b">
            <th className="py-1">Player</th><th>Pos</th><th className="text-right">£</th>
            <th className="text-right">xP (5)</th><th></th>
          </tr>
        </thead>
        <tbody>
          {entry.picks.map((p) => (
            <tr key={p.player_id} className="border-b">
              <td className="py-1">{p.web_name}</td>
              <td>{p.position}</td>
              <td className="text-right">{(p.now_cost / 10).toFixed(1)}</td>
              <td className="text-right">{p.xp.toFixed(1)}</td>
              <td>{p.is_captain ? "C" : p.is_vice ? "V" : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
```

- [ ] **Step 4:** `pnpm --filter web test` (the existing api tests still pass; no new test for the pages — they're thin) then `pnpm --filter web build` (must succeed — Next 16 Turbopack). Commit `feat(web): nav shell, link form, squad page with xP`.

---

## Task 9: docs + wiring

- [ ] `README.md` — add a "Link a team" line under Run: `curl -XPOST localhost:8000/link/<FPL_TEAM_ID>` then `GET /entries/<id>`.
- [ ] `docs/plans/2026-08-27-fplguru-master-build-plan.md` — mark **P1a** ✅ (note: no auth — that's sub-plan P1a-auth).
- [ ] `docs/RESUME-foundation.md` — add a P1a section.
- [ ] `test_beat_schedule.py` — ensure it asserts `sync-linked-teams`.
- [ ] Full `python -m pytest -q -W error` + `python -m ruff check .` + `python -m alembic check` → all clean. `pnpm --filter web test` + `build` → clean.
- [ ] Commit `chore: P1a wiring + docs`, then `docs: P1a complete`.

---

## Self-Review

**Spec coverage (master §3 P1a / PRD §4.1, §4.8):**
- Enter manager ID → squad → Tasks 4, 5, 8 ✓
- Chips → `entry/{id}/history/` `chips` is fetched but **not persisted in P1a** (no `chips` column) — noted, add in a follow-up if the dashboard needs it.
- Entry history (rank + weekly delta, history chart) → `GET /entries/{id}/history` (Task 5); the chart itself is a later dashboard polish.
- Mini-league IDs → **out of scope for P1a** (leaderboard is sub-plan P2h).
- NextAuth login (email + Google) → **deferred to P1a-auth** (blocked on OAuth creds / email transport). P1a is entry-id-keyed, no accounts.
- Dashboard nav shell → Task 8 ✓

**Type/name consistency:**
- `sync_entry(entry_id: int) -> int` (returns `linked_team_id`) — Tasks 4, 5, 6 ✓
- Upsert keys: `LinkedTeam` `(fpl_entry_id)`, `EntryGwHistory` `(linked_team_id, gameweek_id)`, `EntryPick` `(linked_team_id, gameweek_id, player_id)` — model `UniqueConstraint` == `_upsert` `index_elements` ✓
- `_MODEL_VERSION = "basic-v1"` reused in `/entries/{id}` xp join ✓
- web `Entry` / `EntryPick` / `EntryHistoryRow` types mirror the API dict keys ✓
- `packages/entrysync` — new workspace member; `requirements-dev.txt` gets `-e ./packages/entrysync`; `services/{api,worker}` deps get `fplguru-entrysync` ✓

**Placeholder scan:** Task 5 Step 1's `test_link_creates_and_returns_entry` needs the `monkeypatch` rework spelled out inline (noted). Everything else is complete code.

---

## Execution Handoff

Branch `feature/p1a-team-dashboard` off `main`. Subagent-driven. Recommended order: **6 (entrysync skeleton) → 1 → 2 → 3 → 4 → 5 → 7 → 8 → 9**. Tasks 4 & 5 get full review; the rest spec-check.
