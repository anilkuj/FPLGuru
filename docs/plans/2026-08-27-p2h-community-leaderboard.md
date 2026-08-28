# P2h — Community Leaderboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Show a linked team its mini-leagues (rank + weekly delta), full per-league standings with manager search, and its own overall-rank history chart.

**Architecture:** `sync_entry` (P1a) already pulls the manager profile — extend it to capture the profile's `leagues.classic` list into a new `linked_team_leagues` table (id, name, current + last rank). A worker task `sync_league_standings` fetches page 1 (top 50) of `leagues-classic/{id}/standings/` for every distinct tracked league into `league_standings`. The read API exposes the mini-league summary, a stored standings page, a manager search over stored standings, and a rank-history series straight from the existing `entry_gw_history.overall_rank`. The web `/leagues` route lists the mini-leagues and drills into one; a small SVG sparkline renders the rank history.

**Tech Stack:** SQLAlchemy + Alembic (`0008`), Celery + Beat, FastAPI, Next.js 16, Vitest 4. All data from the public FPL API — no new credentials.

---

## Project context (read once)

Same monorepo / SAC toolchain / TDD / commit conventions as the recent plans — re-read the
"Project context" block in [`docs/plans/2026-08-27-p1e-alerts-engine.md`](2026-08-27-p1e-alerts-engine.md).
Branch: **`feature/p2h-leaderboard`** off `main`.

P2h-specific facts:
- `packages/entrysync/src/fplguru_entrysync/__init__.py` — `sync_entry(entry_id)` fetches
  `client.entry(id)` (profile) + `client.entry_history(id)`, upserts `LinkedTeam` + `EntryGwHistory`
  + `EntryPick` inside one `async with get_sessionmaker()() as session, session.begin():`. It has a
  local `_upsert(session, model, rows, keys)` helper (conflict on `keys`, always bumps `updated_at`).
- The FPL profile payload (`entry/{id}/`) has `leagues.classic` = list of
  `{id, name, entry_rank, entry_last_rank, ...}`.
- `EntryGwHistory` columns include `gameweek_id, overall_rank, points, total_points` per linked team.
- `packages/ingest/src/fplguru_ingest/fpl.py` — `normalize_entry`, `normalize_entry_history`;
  tests in `packages/ingest/tests/test_fpl_normalizers.py`, fixture `entry_sample.json`.
- `packages/fpl_client/src/fplguru_fpl_client/client.py` — `FplClient` with `_get(path)`; methods
  like `entry`, `entry_history`, `entry_picks`. Tests use `respx` against `BASE`.
- API `main.py`: `_linked_or_404(db, entry_id)`, `get_db` (read-only). Worker `tasks.py`:
  `_run_and_dispose`, `_record`, `_log_error`, `_upsert`, Beat in `app.py`
  (+ assertion in `services/worker/tests/test_beat_schedule.py`).
- **Baseline:** repo-root `python -m pytest -q` → **146 passed**; web `vitest run` → **11 passed**.

---

## File Structure

| File | Responsibility |
|---|---|
| `packages/core/src/fplguru_core/models.py` | `LinkedTeamLeague`, `LeagueStanding` models. |
| `alembic/versions/0008_leagues.py` | the two tables. |
| `packages/fpl_client/.../client.py` | `FplClient.league_standings(league_id, page)`. |
| `packages/ingest/.../fpl.py` | `normalize_entry` emits `leagues`; new `normalize_league_standings`. |
| `packages/entrysync/.../__init__.py` | `sync_entry` upserts `linked_team_leagues`. |
| `services/worker/.../tasks.py` + `app.py` | `sync_league_standings` task + Beat entry. |
| `services/api/.../main.py` | `GET /entries/{id}/leagues`, `GET /leagues/{id}/standings`, `GET /leagues/{id}/search`, `GET /entries/{id}/rank-history`. |
| `apps/web/src/lib/api.ts` | league + rank-history clients + types. |
| `apps/web/src/app/leagues/page.tsx`, `leagues/[id]/page.tsx`, `leagues/LeagueList.tsx`, `leagues/StandingsTable.tsx`, `leagues/RankSparkline.tsx` | the UI. |
| `apps/web/src/app/layout.tsx` | nav link `Leagues`. |

---

## Task 1: models + `0008` migration

**Files:** `packages/core/src/fplguru_core/models.py`, `packages/core/tests/test_models.py`, `packages/core/tests/test_league_model.py` (new), `alembic/versions/0008_leagues.py` (new).

- [ ] **Step 1: failing test** — `packages/core/tests/test_league_model.py`:
```python
from fplguru_core.models import Base, LeagueStanding, LinkedTeamLeague


def test_league_tables_registered_with_unique_keys():
    assert {"linked_team_leagues", "league_standings"} <= set(Base.metadata.tables)
    ltl = {tuple(sorted(c.name for c in con.columns))
           for con in LinkedTeamLeague.__table__.constraints
           if con.__class__.__name__ == "UniqueConstraint"}
    assert ("league_id", "linked_team_id") in ltl
    ls = {tuple(sorted(c.name for c in con.columns))
          for con in LeagueStanding.__table__.constraints
          if con.__class__.__name__ == "UniqueConstraint"}
    assert ("entry_id", "league_id") in ls
```
Add `"linked_team_leagues"`, `"league_standings"` to `test_models.py::test_expected_tables_registered`.

- [ ] **Step 2: models** — after `class PushSubscription`:
```python
class LinkedTeamLeague(_TimestampMixin, Base):
    """A classic mini-league a linked team belongs to (from the entry profile)."""
    __tablename__ = "linked_team_leagues"
    __table_args__ = (
        UniqueConstraint("linked_team_id", "league_id",
                         name="uq_linked_team_leagues_linked_team_id_league_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    linked_team_id: Mapped[int] = mapped_column(ForeignKey("linked_teams.id"), index=True)
    league_id: Mapped[int] = mapped_column(Integer, index=True)
    league_name: Mapped[str] = mapped_column(String(128), default="")
    entry_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entry_last_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)


class LeagueStanding(_TimestampMixin, Base):
    """A row of a classic-league standings page (top slice), refreshed by a worker task."""
    __tablename__ = "league_standings"
    __table_args__ = (
        UniqueConstraint("league_id", "entry_id",
                         name="uq_league_standings_league_id_entry_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    league_id: Mapped[int] = mapped_column(Integer, index=True)
    entry_id: Mapped[int] = mapped_column(Integer, index=True)
    entry_name: Mapped[str] = mapped_column(String(128), default="")
    player_name: Mapped[str] = mapped_column(String(128), default="")
    rank: Mapped[int] = mapped_column(Integer)
    last_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    event_total: Mapped[int] = mapped_column(Integer, default=0)
```

- [ ] **Step 3: migration `alembic/versions/0008_leagues.py`** (`revision='0008'`, `down_revision='0007'`; style from `0003_entry_tables.py`):
```python
def upgrade() -> None:
    op.create_table(
        'linked_team_leagues',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('linked_team_id', sa.BigInteger(), nullable=False),
        sa.Column('league_id', sa.Integer(), nullable=False),
        sa.Column('league_name', sa.String(length=128), nullable=False),
        sa.Column('entry_rank', sa.Integer(), nullable=True),
        sa.Column('entry_last_rank', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['linked_team_id'], ['linked_teams.id'],
            name=op.f('fk_linked_team_leagues_linked_team_id_linked_teams')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_linked_team_leagues')),
        sa.UniqueConstraint('linked_team_id', 'league_id',
            name='uq_linked_team_leagues_linked_team_id_league_id'),
    )
    op.create_index(op.f('ix_linked_team_leagues_league_id'), 'linked_team_leagues',
                    ['league_id'], unique=False)
    op.create_index(op.f('ix_linked_team_leagues_linked_team_id'), 'linked_team_leagues',
                    ['linked_team_id'], unique=False)
    op.create_table(
        'league_standings',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('league_id', sa.Integer(), nullable=False),
        sa.Column('entry_id', sa.Integer(), nullable=False),
        sa.Column('entry_name', sa.String(length=128), nullable=False),
        sa.Column('player_name', sa.String(length=128), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('last_rank', sa.Integer(), nullable=True),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('event_total', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_league_standings')),
        sa.UniqueConstraint('league_id', 'entry_id',
            name='uq_league_standings_league_id_entry_id'),
    )
    op.create_index(op.f('ix_league_standings_entry_id'), 'league_standings',
                    ['entry_id'], unique=False)
    op.create_index(op.f('ix_league_standings_league_id'), 'league_standings',
                    ['league_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_league_standings_league_id'), table_name='league_standings')
    op.drop_index(op.f('ix_league_standings_entry_id'), table_name='league_standings')
    op.drop_table('league_standings')
    op.drop_index(op.f('ix_linked_team_leagues_linked_team_id'), table_name='linked_team_leagues')
    op.drop_index(op.f('ix_linked_team_leagues_league_id'), table_name='linked_team_leagues')
    op.drop_table('linked_team_leagues')
```

- [ ] **Step 4:** `python -m alembic upgrade head`; `python -m alembic check` → clean. `python -m pytest packages/core -q` → pass. `python -m pytest -q -W error` → **148 passed** (146 + 2). `ruff` clean.
  `feat(core): linked_team_leagues + league_standings tables (0008)`

---

## Task 2: FPL client + normalizers

**Files:** `packages/fpl_client/src/fplguru_fpl_client/client.py`, `packages/ingest/src/fplguru_ingest/fpl.py`, `packages/ingest/tests/test_fpl_normalizers.py`, `packages/ingest/tests/fixtures/entry_sample.json`, `packages/ingest/tests/fixtures/league_standings_sample.json` (new), `packages/fpl_client/tests/test_client.py`.

- [ ] **Step 1: fixtures**

Append `"leagues"` to `packages/ingest/tests/fixtures/entry_sample.json`:
```json
{"id": 7, "name": "My Team", "player_first_name": "Sam", "player_last_name": "Q",
 "started_event": 1, "favourite_team": 3,
 "leagues": {"classic": [
   {"id": 111, "name": "Work League", "entry_rank": 4, "entry_last_rank": 6},
   {"id": 314, "name": "Overall", "entry_rank": 900000, "entry_last_rank": 950000}
 ]}}
```

`packages/ingest/tests/fixtures/league_standings_sample.json`:
```json
{"league": {"id": 111, "name": "Work League"},
 "standings": {"has_next": true, "page": 1, "results": [
   {"entry": 7, "entry_name": "My Team", "player_name": "Sam Q",
    "rank": 4, "last_rank": 6, "total": 512, "event_total": 61},
   {"entry": 99, "entry_name": "Rival FC", "player_name": "Alex P",
    "rank": 5, "last_rank": 3, "total": 508, "event_total": 44}
 ]}}
```

- [ ] **Step 2: failing tests**

`packages/ingest/tests/test_fpl_normalizers.py` — **update the existing `test_normalize_entry`**
(exact-dict `==`) to add the new key:
```python
def test_normalize_entry():
    assert normalize_entry(ENTRY) == {
        "fpl_entry_id": 7, "manager_name": "Sam Q", "started_event": 1, "favourite_team_id": 3,
        "leagues": [
            {"league_id": 111, "league_name": "Work League", "entry_rank": 4,
             "entry_last_rank": 6},
            {"league_id": 314, "league_name": "Overall", "entry_rank": 900000,
             "entry_last_rank": 950000},
        ],
    }
```
then append:
```python
def test_normalize_entry_includes_classic_leagues():
    row = normalize_entry(json.loads((FIX / "entry_sample.json").read_text()))
    assert row["leagues"] == [
        {"league_id": 111, "league_name": "Work League", "entry_rank": 4, "entry_last_rank": 6},
        {"league_id": 314, "league_name": "Overall", "entry_rank": 900000,
         "entry_last_rank": 950000},
    ]


def test_normalize_league_standings_maps_rows():
    from fplguru_ingest.fpl import normalize_league_standings

    payload = json.loads((FIX / "league_standings_sample.json").read_text())
    out = normalize_league_standings(111, payload)
    assert out["league_name"] == "Work League"
    assert out["has_next"] is True
    assert out["rows"][0] == {
        "league_id": 111, "entry_id": 7, "entry_name": "My Team", "player_name": "Sam Q",
        "rank": 4, "last_rank": 6, "total": 512, "event_total": 61,
    }
```
(`FIX` / `json` are already imported at the top of that test file.)

`packages/fpl_client/tests/test_client.py` (append a test mirroring the existing style):
```python
@respx.mock
async def test_league_standings_hits_paged_endpoint():
    route = respx.get(f"{BASE}/leagues-classic/111/standings/").mock(
        return_value=httpx.Response(200, json={"league": {}, "standings": {"results": []}})
    )
    async with FplClient(BASE) as c:
        await c.league_standings(111, page=2)
    assert route.called
    assert route.calls.last.request.url.params["page_standings"] == "2"
```
(match the import names / `BASE` / async-fixture style already in that file.)

- [ ] **Step 3: implement**

`client.py` — after `entry_picks`:
```python
    async def league_standings(self, league_id: int, page: int = 1) -> dict:
        return await self._get(
            f"leagues-classic/{league_id}/standings/?page_standings={page}"
        )
```

`fpl.py` — in `normalize_entry`, add before `return`:
```python
    leagues = [
        {"league_id": lg["id"], "league_name": lg.get("name", ""),
         "entry_rank": lg.get("entry_rank"), "entry_last_rank": lg.get("entry_last_rank")}
        for lg in payload.get("leagues", {}).get("classic", [])
    ]
```
and add `"leagues": leagues` to the returned dict. Then a new function:
```python
def normalize_league_standings(league_id: int, payload: dict[str, Any]) -> dict:
    st = payload.get("standings", {})
    rows = [
        {
            "league_id": league_id,
            "entry_id": r["entry"],
            "entry_name": r.get("entry_name", ""),
            "player_name": r.get("player_name", ""),
            "rank": r["rank"],
            "last_rank": r.get("last_rank"),
            "total": r.get("total", 0),
            "event_total": r.get("event_total", 0),
        }
        for r in st.get("results", [])
    ]
    return {
        "league_name": payload.get("league", {}).get("name", ""),
        "has_next": bool(st.get("has_next", False)),
        "rows": rows,
    }
```

- [ ] **Step 4:** `python -m pytest packages/ingest packages/fpl_client -q` → pass. `python -m pytest -q -W error` → **151 passed** (148 + 3). `ruff` clean.
  `feat(fpl): league standings client + normalizers`

---

## Task 3: `sync_entry` captures mini-leagues

**Files:** `packages/entrysync/src/fplguru_entrysync/__init__.py`, `packages/entrysync/tests/` (add a test file or extend the existing one).

- [ ] **Step 1: failing test** — in the entrysync test module (mirror the existing `respx` setup that stubs `entry` / `entry_history` / picks):
```python
async def test_sync_entry_upserts_mini_leagues(db_session):
    # ... existing respx stubs for entry (with a leagues.classic list), history, picks ...
    lt_id = await sync_entry(7)
    rows = (await db_session.execute(
        select(LinkedTeamLeague).where(LinkedTeamLeague.linked_team_id == lt_id)
        .order_by(LinkedTeamLeague.league_id)
    )).scalars().all()
    assert [(r.league_id, r.league_name, r.entry_rank) for r in rows] == [
        (111, "Work League", 4), (314, "Overall", 900000),
    ]
    # re-sync with a changed rank -> upsert, not duplicate
    # (re-stub entry with entry_rank 3 for league 111, call sync_entry(7) again)
    rows = (await db_session.execute(
        select(LinkedTeamLeague).where(LinkedTeamLeague.linked_team_id == lt_id)
    )).scalars().all()
    assert len(rows) == 2
```
Make the `entry` stub payload include:
`"leagues": {"classic": [{"id": 111, "name": "Work League", "entry_rank": 4, "entry_last_rank": 6}, {"id": 314, "name": "Overall", "entry_rank": 900000, "entry_last_rank": 950000}]}`.

- [ ] **Step 2: implement** — import `LinkedTeamLeague` in `__init__.py`.

  **Critical:** `sync_entry` does `lt = LinkedTeam(**ent, last_synced_at=...)`. `ent` now carries a
  `"leagues"` key that is **not** a `LinkedTeam` column — you must pop it first. Right after
  `ent = normalize_entry(profile)` (just above the `async with ... session.begin()` block):
  ```python
      leagues = ent.pop("leagues", [])
  ```
  Then after the `EntryGwHistory` upsert inside the `session.begin()` block:
  ```python
          league_rows = [{"linked_team_id": lt_id, **lg} for lg in leagues]
          await _upsert(session, LinkedTeamLeague, league_rows,
                        ("linked_team_id", "league_id"))
  ```
  (`_upsert` is a no-op on an empty list.)

- [ ] **Step 3:** run the entrysync tests → green. `python -m pytest -q -W error` → **152 passed** (151 + 1). `ruff` clean.
  `feat(entrysync): capture a linked team's classic mini-leagues`

---

## Task 4: worker `sync_league_standings`

**Files:** `services/worker/src/fplguru_worker/tasks.py`, `services/worker/src/fplguru_worker/app.py`, `services/worker/tests/test_beat_schedule.py`, `services/worker/tests/test_sync_league_standings.py` (new).

- [ ] **Step 1: failing test** — `services/worker/tests/test_sync_league_standings.py`:
```python
from datetime import UTC, datetime

from sqlalchemy import select

from fplguru_core.models import LeagueStanding, LinkedTeam, LinkedTeamLeague
from fplguru_worker import tasks

_STANDINGS = {
    111: {"league": {"name": "Work League"},
          "standings": {"has_next": False, "results": [
              {"entry": 7, "entry_name": "My Team", "player_name": "Sam Q",
               "rank": 1, "last_rank": 2, "total": 500, "event_total": 60},
          ]}},
    222: {"league": {"name": "Cup"},
          "standings": {"has_next": False, "results": [
              {"entry": 8, "entry_name": "Other", "player_name": "Jo K",
               "rank": 3, "last_rank": 3, "total": 400, "event_total": 40},
          ]}},
}


class _FakeClient:
    def __init__(self, base):
        pass

    async def league_standings(self, league_id, page=1):
        return _STANDINGS[league_id]

    async def aclose(self):
        pass


async def _seed(db_session):
    db_session.add_all([
        LinkedTeam(id=1, fpl_entry_id=7, manager_name="Sam"),
        LinkedTeam(id=2, fpl_entry_id=8, manager_name="Jo"),
    ])
    await db_session.commit()
    db_session.add_all([
        LinkedTeamLeague(linked_team_id=1, league_id=111, league_name="Work League"),
        LinkedTeamLeague(linked_team_id=1, league_id=222, league_name="Cup"),
        LinkedTeamLeague(linked_team_id=2, league_id=222, league_name="Cup"),  # shared
    ])
    await db_session.commit()


async def test_sync_league_standings_fetches_each_distinct_league_once(db_session, monkeypatch):
    await _seed(db_session)
    monkeypatch.setattr(tasks, "FplClient", _FakeClient)
    await tasks._sync_league_standings()

    rows = (await db_session.execute(
        select(LeagueStanding).order_by(LeagueStanding.league_id)
    )).scalars().all()
    assert [(r.league_id, r.entry_id, r.rank) for r in rows] == [(111, 7, 1), (222, 8, 3)]

    # idempotent
    await tasks._sync_league_standings()
    rows = (await db_session.execute(select(LeagueStanding))).scalars().all()
    assert len(rows) == 2
```

- [ ] **Step 2: implement in `tasks.py`** — import `LeagueStanding`, `LinkedTeamLeague`; `from fplguru_ingest.fpl import normalize_league_standings` (add to that import block). Add after `_sync_linked_teams`:
```python
async def _upsert_standings(session, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(LeagueStanding).values(rows)
    cols = {c: stmt.excluded[c] for c in rows[0] if c not in ("league_id", "entry_id")}
    cols["updated_at"] = func.now()
    await session.execute(stmt.on_conflict_do_update(
        index_elements=["league_id", "entry_id"], set_=cols))


async def _sync_league_standings() -> None:
    started = datetime.now(UTC)
    try:
        async with get_sessionmaker()() as session:
            league_ids = sorted({
                lid for (lid,) in (await session.execute(
                    select(LinkedTeamLeague.league_id).distinct()
                )).all()
            })
        client = FplClient(get_settings().fpl_api_base)
        total = 0
        try:
            for lid in league_ids:
                payload = await client.league_standings(lid, page=1)
                norm = normalize_league_standings(lid, payload)
                async with get_sessionmaker()() as session, session.begin():
                    await _upsert_standings(session, norm["rows"])
                total += len(norm["rows"])
        finally:
            await client.aclose()
        async with get_sessionmaker()() as session, session.begin():
            await _record(session, "leagues", "ok", started,
                          f"{total} rows over {len(league_ids)} leagues")
        logger.info("league standings synced: %d rows / %d leagues", total, len(league_ids))
    except Exception as exc:
        await _log_error("leagues", started, exc)
        raise


@celery_app.task(name="sync_league_standings", bind=True, max_retries=2, default_retry_delay=120)
def sync_league_standings(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_sync_league_standings))
    except Exception as exc:
        raise self.retry(exc=exc) from exc
```

- [ ] **Step 3: Beat + assertion** — `app.py`: `"sync-league-standings": {"task": "sync_league_standings", "schedule": 7200.0}`. `test_beat_schedule.py`: `assert sched["sync-league-standings"]["task"] == "sync_league_standings"`.

- [ ] **Step 4:** `python -m pytest services/worker/tests/test_sync_league_standings.py services/worker/tests/test_beat_schedule.py -q` → **3 passed**. `python -m pytest -q -W error` → **155 passed** (152 + 3). `ruff` clean, `alembic check` clean.
  `feat(worker): sync_league_standings task`

---

## Task 5: API endpoints

**Files:** `services/api/src/fplguru_api/main.py`, `services/api/tests/test_leagues_api.py` (new).

- [ ] **Step 1: failing test** — `services/api/tests/test_leagues_api.py`:
```python
from datetime import UTC, datetime

from fplguru_core.models import (
    EntryGwHistory, Gameweek, LeagueStanding, LinkedTeam, LinkedTeamLeague,
)


async def _seed(db_session):
    db_session.add_all([
        Gameweek(id=1, name="GW1", deadline_time=datetime(2025, 8, 1, tzinfo=UTC)),
        Gameweek(id=2, name="GW2", deadline_time=datetime(2025, 8, 8, tzinfo=UTC)),
        LinkedTeam(id=1, fpl_entry_id=7, manager_name="Sam"),
    ])
    await db_session.commit()
    db_session.add_all([
        LinkedTeamLeague(linked_team_id=1, league_id=111, league_name="Work League",
                         entry_rank=4, entry_last_rank=6),
        EntryGwHistory(linked_team_id=1, gameweek_id=1, points=60, total_points=60,
                       overall_rank=1_000_000, bank=0, team_value=1000, transfers=0,
                       transfer_cost=0, points_on_bench=5),
        EntryGwHistory(linked_team_id=1, gameweek_id=2, points=70, total_points=130,
                       overall_rank=800_000, bank=0, team_value=1001, transfers=1,
                       transfer_cost=0, points_on_bench=2),
        LeagueStanding(league_id=111, entry_id=7, entry_name="My Team", player_name="Sam Q",
                       rank=4, last_rank=6, total=512, event_total=61),
        LeagueStanding(league_id=111, entry_id=99, entry_name="Rival FC", player_name="Alex P",
                       rank=5, last_rank=3, total=508, event_total=44),
    ])
    await db_session.commit()


async def test_entry_leagues_lists_mini_leagues_with_delta(client, db_session):
    await _seed(db_session)
    body = (await client.get("/entries/7/leagues")).json()
    assert body[0]["league_id"] == 111
    assert body[0]["entry_rank"] == 4 and body[0]["delta"] == 2      # 6 -> 4 = +2 (improved)


async def test_league_standings_endpoint_sorted_by_rank(client, db_session):
    await _seed(db_session)
    body = (await client.get("/leagues/111/standings")).json()
    assert body["league_id"] == 111
    assert [r["rank"] for r in body["standings"]] == [4, 5]
    assert body["standings"][0]["delta"] == 2


async def test_league_search(client, db_session):
    await _seed(db_session)
    body = (await client.get("/leagues/111/search?q=rival")).json()
    assert [r["entry_id"] for r in body] == [99]


async def test_rank_history(client, db_session):
    await _seed(db_session)
    body = (await client.get("/entries/7/rank-history")).json()
    assert [(r["gameweek_id"], r["overall_rank"]) for r in body] == [(1, 1_000_000), (2, 800_000)]


async def test_leagues_unknown_entry_404(client, db_session):
    assert (await client.get("/entries/999/leagues")).status_code == 404
```

- [ ] **Step 2: implement in `main.py`** — add `EntryGwHistory` (already imported), `LeagueStanding`, `LinkedTeamLeague` to the models import. Add a helper + routes:
```python
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
            func.lower(LeagueStanding.entry_name).like(func.lower(like))
            | func.lower(LeagueStanding.player_name).like(func.lower(like)),
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
```

- [ ] **Step 3:** `python -m pytest services/api/tests/test_leagues_api.py -q` → **5 passed**. `python -m pytest -q -W error` → **160 passed** (155 + 5). `ruff` clean.
  `feat(api): mini-leagues, standings, search, rank-history`

---

## Task 6: web API client

**Files:** `apps/web/src/lib/api.ts`, `apps/web/src/lib/api.leagues.test.ts` (new).

- [ ] **Step 1: failing test** — `apps/web/src/lib/api.leagues.test.ts`:
```ts
import { describe, expect, it, vi } from "vitest";

import { getEntryLeagues, getLeagueStandings, getRankHistory } from "./api";

const ok = (json: unknown) => ({ ok: true, json: async () => json });

describe("leagues api", () => {
  it("getEntryLeagues", async () => {
    const f = vi.fn().mockResolvedValue(ok([{ league_id: 1, delta: 2 }]));
    global.fetch = f as unknown as typeof fetch;
    const r = await getEntryLeagues("http://api.test", 7);
    expect(r[0].delta).toBe(2);
    expect(String(f.mock.calls[0][0])).toContain("/entries/7/leagues");
  });

  it("getLeagueStandings", async () => {
    const f = vi.fn().mockResolvedValue(ok({ league_id: 1, standings: [] }));
    global.fetch = f as unknown as typeof fetch;
    await getLeagueStandings("http://api.test", 1);
    expect(String(f.mock.calls[0][0])).toContain("/leagues/1/standings");
  });

  it("getRankHistory", async () => {
    const f = vi.fn().mockResolvedValue(ok([{ gameweek_id: 1, overall_rank: 10 }]));
    global.fetch = f as unknown as typeof fetch;
    const r = await getRankHistory("http://api.test", 7);
    expect(r[0].overall_rank).toBe(10);
  });
});
```

- [ ] **Step 2: implement** — append to `apps/web/src/lib/api.ts`:
```ts
export type MiniLeague = {
  league_id: number;
  league_name: string;
  entry_rank: number | null;
  entry_last_rank: number | null;
  delta: number | null;
};
export type StandingRow = {
  entry_id: number;
  entry_name: string;
  player_name: string;
  rank: number;
  last_rank: number | null;
  total: number;
  event_total: number;
  delta: number | null;
};
export type LeagueStandings = { league_id: number; standings: StandingRow[] };
export type RankPoint = {
  gameweek_id: number;
  overall_rank: number | null;
  points: number;
  total_points: number;
};

export function getEntryLeagues(base: string, entryId: number) {
  return fetch(`${base}/entries/${entryId}/leagues`, { cache: "no-store" }).then(
    asJson<MiniLeague[]>,
  );
}
export function getLeagueStandings(base: string, leagueId: number) {
  return fetch(`${base}/leagues/${leagueId}/standings`, { cache: "no-store" }).then(
    asJson<LeagueStandings>,
  );
}
export function searchLeague(base: string, leagueId: number, q: string) {
  return fetch(`${base}/leagues/${leagueId}/search?q=${encodeURIComponent(q)}`, {
    cache: "no-store",
  }).then(asJson<Array<Pick<StandingRow, "entry_id" | "entry_name" | "player_name" | "rank" | "total">>>);
}
export function getRankHistory(base: string, entryId: number) {
  return fetch(`${base}/entries/${entryId}/rank-history`, { cache: "no-store" }).then(
    asJson<RankPoint[]>,
  );
}
```

- [ ] **Step 3:** `./node_modules/.bin/vitest run` → **14 passed** (11 + 3).
  `feat(web): league + rank-history API clients`

---

## Task 7: web `/leagues` pages + nav + sparkline

**Files:** create `apps/web/src/app/leagues/page.tsx`, `leagues/LeagueList.tsx`, `leagues/RankSparkline.tsx`, `leagues/[id]/page.tsx`, `leagues/[id]/StandingsView.tsx`; modify `apps/web/src/app/layout.tsx`.

- [ ] **Step 1: `leagues/RankSparkline.tsx`** (pure, no client hooks needed — a plain component):
```tsx
import type { RankPoint } from "@/lib/api";

export function RankSparkline({ points, width = 240, height = 40 }: {
  points: RankPoint[];
  width?: number;
  height?: number;
}) {
  const vals = points.map((p) => p.overall_rank).filter((r): r is number => r != null);
  if (vals.length < 2) return null;
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  // lower rank = better = higher on the chart
  const d = vals
    .map((r, i) => {
      const x = (i / (vals.length - 1)) * (width - 2) + 1;
      const y = ((r - min) / span) * (height - 2) + 1;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg width={width} height={height} className="text-sky-400">
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}
```

- [ ] **Step 2: `leagues/LeagueList.tsx`** (client) — reads `getStoredEntryId`, `getEntryLeagues` + `getRankHistory` on mount; renders the sparkline then a list of leagues (name, `entry_rank`, a ▲+n / ▼-n / – delta), each an `<a href={`/leagues/${id}`}>`. "Link your team first" when no entry id. Keep it compact, styled like the other pages.

- [ ] **Step 3: `leagues/page.tsx`** (server shell) → `<main className="p-8"><h1>Leagues</h1><LeagueList /></main>`.

- [ ] **Step 4: `leagues/[id]/StandingsView.tsx`** (client) — `params`-passed `leagueId` (see below); `getLeagueStandings` on mount into a table (rank, delta, manager, team, GW, total); a search `<input>` that calls `searchLeague` and shows matches above the table. `leagues/[id]/page.tsx`:
```tsx
import { StandingsView } from "./StandingsView";

export default async function LeaguePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">League standings</h1>
      <StandingsView leagueId={Number(id)} />
    </main>
  );
}
```
(Next 16 route params are async — `await params`.)

- [ ] **Step 5: `layout.tsx`** — add `<a href="/leagues">Leagues</a>` to the `<nav>` after `/live`.

- [ ] **Step 6:** `./node_modules/.bin/vitest run` → **14 passed** (unchanged). `./node_modules/.bin/next build` → success; route list shows `/leagues` and `/leagues/[id]` (the latter as a dynamic `ƒ` route — that is fine, it fetches client-side).
  `feat(web): /leagues mini-league board, standings + search, rank sparkline`

---

## Task 8: docs

**Files:** `README.md`, `docs/plans/2026-08-27-fplguru-master-build-plan.md`, `docs/RESUME-foundation.md`.

- [ ] **Step 1: `README.md`** — new "Leagues" section: `sync_entry` captures the manager's classic mini-leagues; `sync_league_standings` (Beat, 2h) refreshes the top slice of each tracked league. Endpoints `GET /entries/{id}/leagues`, `GET /leagues/{id}/standings`, `GET /leagues/{id}/search?q=`, `GET /entries/{id}/rank-history`. Add `sync_league_standings` to the worker task list.
- [ ] **Step 2: master plan** — mark **P2h** ✅ (branch `feature/p2h-leaderboard`), one-line summary; decrement remaining count. Note "global leaderboard = the FPL 'Overall' league (id 314) captured like any other mini-league the manager is in; a dedicated global top-N crawl is a follow-up".
- [ ] **Step 3: `docs/RESUME-foundation.md`** — top status line + a `## P2h` section (task table + commits) + note the first Phase-2 sub-plan is done and the rest of the blocked/unblocked split is unchanged.
- [ ] **Step 4: full verification** — `pytest -q -W error` → **160 passed**; `ruff` clean; `alembic check` clean; web `vitest run` → 14 passed; `next build` → success.
- [ ] **Step 5:** `docs: P2h Community Leaderboard complete`

---

## Self-Review

**Spec coverage (master §3 P2h / PRD §4.8):**
- Global + mini-league boards → mini-leagues from the profile; "global" = the Overall league (314) if the manager is in it (they always are). A separate global top-N crawler is a documented follow-up ✓ (partial — global is via the Overall league, not a bespoke crawl)
- rank + weekly delta → `entry_rank` / `entry_last_rank` on the mini-league summary; `rank` / `last_rank` per standings row; `_delta` = `last - rank` (positive = moved up) ✓
- manager search → `GET /leagues/{id}/search?q=` ILIKE over stored standings (scoped to a league) ✓
- rank-history chart → `GET /entries/{id}/rank-history` from `entry_gw_history.overall_rank` + `RankSparkline` SVG ✓

**Type/name consistency:**
- `normalize_entry` now returns `leagues: [{league_id, league_name, entry_rank, entry_last_rank}]` — consumed by `sync_entry` → `LinkedTeamLeague` columns (+ `linked_team_id`) ✓
- `normalize_league_standings(league_id, payload) -> {league_name, has_next, rows}`; `rows[i]` keys == `LeagueStanding` columns (minus `id`) == `_upsert_standings` conflict-safe set ✓
- `LinkedTeamLeague` uq `(linked_team_id, league_id)` == entrysync `_upsert` keys == migration; `LeagueStanding` uq `(league_id, entry_id)` == `_upsert_standings` `index_elements` == migration ✓
- API JSON (`league_id, league_name, entry_rank, entry_last_rank, delta` / `entry_id, entry_name, player_name, rank, last_rank, total, event_total, delta` / `gameweek_id, overall_rank, points, total_points`) == web `MiniLeague` / `StandingRow` / `RankPoint` ✓
- `FplClient.league_standings(league_id, page)` — Task 2 def == Task 4 call ✓

**Migration drift:** `0008` adds two tables (no FK on `league_standings` — `entry_id` is an FPL id, not a local `linked_teams` row); `alembic check` in Task 1 Step 4; `test_expected_tables_registered` updated same task.

**Placeholder scan:** Tasks 2/3/7 lean on "mirror the existing test style" for `respx`/entrysync setup and the two client web components — acceptable for spec-check (the shapes and assertions are fully given); the implementer fills the boilerplate.

---

## Execution Handoff

Branch `feature/p2h-leaderboard` off `main`. Subagent-driven, order 1 → 8. Task 2 (normalizers) + Task 4 (worker) + Task 5 (API) get a full review; Tasks 1, 3, 6 spec-check + quality-check; Tasks 7, 8 spec-check. After Task 8: whole-branch review, PR → `main`, watch CI, squash-merge.

### Deferred follow-ups
- Dedicated global top-N leaderboard crawl (paginate the Overall league, cache aggressively).
- Standings pagination (`has_next` from `normalize_league_standings` is captured but unused — API returns only page 1 / top `limit`).
- H2H leagues (`leagues.h2h`) — different standings shape.
- Mini-league movers/shakers alert generator (ties into P1e).
