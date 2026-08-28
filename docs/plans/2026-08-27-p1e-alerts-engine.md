# P1e — Alerts Engine + Priority Ranking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development — one implementer subagent per task, then a spec-compliance review and a code-quality review, fix loop, commit, next task. Steps use `- [ ]` checkboxes.

**Goal:** Generate per-linked-team alerts (player availability changes, blank/double gameweeks), rank them by a documented priority score, cap them to a user-configurable number, and serve them as an in-app feed with an unseen badge.

**Architecture:** A new pure package `fplguru-alerts` holds the priority-score function and the generator functions (state in → alert dicts out). A worker task `generate_alerts` runs the generators per linked team on a Beat cadence, upserts rows into a new `alerts` table keyed by a stable `dedup_key`, scores them, and marks the lowest-priority ones `suppressed` when the team's `alert_cap` is set. The read-only API serves the feed and accepts "mark seen" + a settings patch. The Next.js `/alerts` page polls the feed and shows an unseen count in the nav.

**Tech Stack:** SQLAlchemy 2.0 async + Alembic (`0005`), Celery + Beat, FastAPI, a new pure package `fplguru-alerts`, Next.js 16 App Router + Vitest 4.

**Scope note (2026-08-27 override — no Free/Pro tiers):** there is no 10-message free cap and no "upgrade" message. Instead `linked_teams.alert_cap` is a nullable int: `NULL` = uncapped (the default); when set, alerts beyond the cap (lowest priority first) are stored but flagged `suppressed` and hidden from the default feed. **Web Push delivery is deferred to P1h** (which owns VAPID + push-subscription management). P1e delivers in-app only; every alert row already carries a push-ready `{title, body, url}` so P1h only needs to add a delivery sink. `price_change` and `fdr_shift` generators need historical snapshots and are **deferred** (follow-ups listed at the end) — v1 ships `availability` and `dgw` / `bgw`.

---

## Project context (read once — every task assumes this)

- **Monorepo** `D:\AntiGravity\FPLGuru`. Work on branch **`feature/p1e-alerts`** off `main`.
- **Toolchain (Smart App Control ON):** `venv` + `pip`, never `uv`. Every tool is `python -m <tool>` (`python -m pytest`, `python -m ruff`, `python -m alembic`). Activate first: `source .venv/Scripts/activate` (Git Bash) or call `.venv/Scripts/python.exe`. Chain shell commands in one call.
- **Docker must be up:** `docker compose -f infra/docker-compose.yml up -d --wait`.
- **New package:** add `-e ./packages/<x>` to `requirements-dev.txt` (after `-e ./packages/live`), add `"fplguru_<x>"` to `[tool.ruff.lint.isort] known-first-party` in root `pyproject.toml`, then `python -m pip install -r requirements-dev.txt`. Copy `packages/live/pyproject.toml`'s shape (hatchling, `src/` layout, `dependencies = []`). No `__init__.py` in `packages/*/tests/`.
- **Models have NO `relationship()`.** Test seeds insert FK-parent rows and `await session.commit()` before children (commit waves). Real `datetime(..., tzinfo=UTC)` for `DateTime(timezone=True)` — asyncpg rejects strings.
- **Migrations:** `alembic/versions/000N_*.py`, `revision`/`down_revision` are plain strings (`'0004'` is current head). CI runs `python -m alembic check` — must stay clean. `alembic/*` is ruff-exempt for `E402,E501,I001,UP035,UP007`. Every migration task also updates `packages/core/tests/test_models.py::test_expected_tables_registered` (exact-set assertion) with the new table name(s). Bool `server_default` in a migration is `sa.text('false')`; match the model's `server_default="false"`.
- **Worker pattern:** each Celery task body is `asyncio.run(_run_and_dispose(_async_fn))`. Async helpers use `async with get_sessionmaker()() as session, session.begin():`. Errors → `_log_error(source, started, exc)` on a fresh session, then `raise`. `_upsert_*` helpers do `pg_insert(...).on_conflict_do_update(index_elements=[...], set_=...)`. Beat entries live in `services/worker/src/fplguru_worker/app.py` `beat_schedule` (add an assertion to `services/worker/tests/test_beat_schedule.py`).
- **API:** `services/api/src/fplguru_api/main.py`. `get_db` yields a read-only `AsyncSession` — a mutating route manages its own transaction with `async with db.begin():`. There is a `_linked_or_404(db, entry_id) -> LinkedTeam` helper and a `_MODEL_VERSION` constant. Imports already include `from fastapi import Depends, FastAPI, HTTPException, Query, Request` and `from sqlalchemy import desc, distinct, func, select, text`. Tests: `services/api/tests/conftest.py` gives `client` (ASGI, `get_db` overridden onto the test DB); root `conftest.py` gives `db_session` + autouse `_point_app_at_test_db`.
- **Web:** `apps/web`, Next 16, Tailwind v4, Vitest 4. `NEXT_PUBLIC_API_BASE` default `http://localhost:8000`. `src/lib/api.ts` has a private `async function asJson<T>(res)` and existing `getEntry`. `src/lib/entry.ts` → `getStoredEntryId()` (localStorage `fplguru.entryId`). `src/lib/prefs.ts` → `getPref`/`setPref`. Pages are server components rendering a `"use client"` child (see `src/app/squad/`, `src/app/live/`). `src/app/layout.tsx` nav is a `<nav>` of `<a>`/`<span>`. Web checks from `apps/web`: `./node_modules/.bin/vitest run`, `./node_modules/.bin/next build`.
- **Commits:** code tasks stage `git add -A -- ':!docs'`; doc tasks stage `docs/` + `README.md` explicitly. Author every commit:
  `git -c user.name="Anil Kujur" -c user.email="anilkuj@gmail.com" commit -m "<msg>" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`
  **Do not push.** One commit per task.
- **TDD:** failing test → run → see it fail for the right reason → minimal impl → green → full suite.
- **Full verification before every task commit:** `python -m pytest -q -W error` (repo root), `python -m ruff check .`, `python -m alembic check`. Web tasks also `./node_modules/.bin/vitest run` + `./node_modules/.bin/next build`.

**Baseline:** repo-root `python -m pytest -q` is currently **109 passed**; web `vitest run` is **5 passed**. Each task states the new expected count.

---

## File Structure

| File | Responsibility |
|---|---|
| `docs/design/2026-08-27-alert-priority-ranking.md` (new) | The priority-score rationale, formula, worked examples. |
| `packages/alerts/` (new pkg `fplguru-alerts`) | Pure: `score_alert(...)`, `availability_alerts(...)`, `dgw_bgw_alerts(...)`. No DB, no network. |
| `packages/core/src/fplguru_core/models.py` | `Alert` model; `LinkedTeam` gains `alert_cap`. |
| `alembic/versions/0005_alerts.py` | Create `alerts`; add `linked_teams.alert_cap`. |
| `services/worker/src/fplguru_worker/tasks.py` | `_generate_alerts` helper + `generate_alerts` task (+ cap application). |
| `services/worker/src/fplguru_worker/app.py` | Beat entry `generate-alerts`. |
| `services/api/src/fplguru_api/main.py` | `GET /entries/{id}/alerts`, `POST /entries/{id}/alerts/seen`, `PATCH /entries/{id}/settings`. |
| `apps/web/src/lib/api.ts` | `Alert` type + `getAlerts` / `markAlertsSeen` / `updateEntrySettings`. |
| `apps/web/src/app/alerts/page.tsx`, `apps/web/src/app/alerts/AlertFeed.tsx` | Feed page (client, 60s poll, mark-all-read, cap control). |
| `apps/web/src/app/layout.tsx` | Nav: greyed `Alerts` (add it) with an unseen-count badge — actually a small client `NavAlerts` island. |

---

## Task 1: priority-ranking design doc

**Files:** Create `docs/design/2026-08-27-alert-priority-ranking.md`.

- [ ] **Step 1: write the doc** with exactly these sections:

```markdown
# Alert Priority Ranking

**Status:** accepted · 2026-08-27 · owner: FPLGuru
**Context:** PRD next-steps §11.4. Feeds sub-plan P1e.

## Problem

When a linked team has more pending alerts than its `alert_cap`, we must decide
which to surface and which to suppress. We need a deterministic, explainable score.

## Score

`score_alert` returns an integer 0–100 (higher = more important). It is a sum of
additive terms, then clamped:

| Term | Value | When |
|---|---|---|
| base: availability | 60 | player availability changed |
| base: bgw | 45 | a team the user owns has no fixture next GW |
| base: dgw | 40 | a team the user owns has 2+ fixtures next GW |
| base: other | 20 | any future generator without an explicit base |
| captaincy | +25 | the affected player is the user's (vice-)captain |
| starting XI | +15 | the affected player has multiplier > 0 (and not captain) |
| hard unavailability | +15 | availability alert whose status is i / s / u (not just "doubtful") |
| pre-deadline | +10 | the current GW deadline has not passed |

Clamp to `[0, 100]`. Ties break by `alert.id` ascending (older first) so ordering
is stable across re-runs.

## Why these weights

- Availability outranks DGW/BGW: a player who won't play is an immediate lineup
  problem; a blank/double is planning information with a longer runway.
- BGW slightly above DGW: a blank can leave you short a starter; a double is upside.
- Captaincy > XI > bench/owned-only: impact scales with how much the pick counts.
- "Hard out" (injured/suspended/unavailable) above "doubtful": less ambiguity, more
  urgency.
- Pre-deadline bump: the alert is still actionable this GW.

## Worked examples

| Alert | Terms | Score |
|---|---|---|
| Captain ruled out (status i), pre-deadline | 60 + 25 + 15 + 10 | 100 (clamped) |
| Bench player doubtful (75%), pre-deadline | 60 + 10 | 70 |
| DGW for a team whose player is in your XI, pre-deadline | 40 + 15 + 10 | 65 |
| BGW for a team you own on the bench, post-deadline | 45 | 45 |

## Cap application

Per linked team, per gameweek: sort that GW's alerts by `(-score, id)`; the first
`alert_cap` stay visible, the rest get `suppressed = true` (still stored, hidden
from the default feed, visible with `?include_suppressed=true`). `alert_cap = NULL`
(default) suppresses nothing.

## Deferred generators

`price_change` (needs a `now_cost` history snapshot) and `fdr_shift` (needs stored
per-GW FDR snapshots) are out of scope for P1e v1; when added they slot in with a
base weight in the table above.
```

- [ ] **Step 2: commit**
```bash
git add docs/design/2026-08-27-alert-priority-ranking.md
git -c user.name="Anil Kujur" -c user.email="anilkuj@gmail.com" commit -m "docs: alert priority-ranking design" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2: `fplguru-alerts` package — score + generators

**Files:**
- Create: `packages/alerts/pyproject.toml`, `packages/alerts/src/fplguru_alerts/__init__.py`, `packages/alerts/tests/test_alerts.py`
- Modify: `requirements-dev.txt`, `pyproject.toml`

- [ ] **Step 1: skeleton** — `packages/alerts/pyproject.toml` like `packages/live/pyproject.toml` with `name = "fplguru-alerts"`, `description = "Pure alert generators + priority scoring."`, `packages = ["src/fplguru_alerts"]`. Add `-e ./packages/alerts` to `requirements-dev.txt` (after `-e ./packages/live`). Add `"fplguru_alerts"` to `known-first-party`. `python -m pip install -r requirements-dev.txt`.

- [ ] **Step 2: failing test** — `packages/alerts/tests/test_alerts.py`:
```python
from fplguru_alerts import availability_alerts, dgw_bgw_alerts, score_alert


def test_score_captain_hard_out_pre_deadline_clamps_to_100():
    a = {"type": "availability", "payload": {"status": "i"}}
    assert score_alert(a, in_xi=True, is_captain=True, before_deadline=True) == 100


def test_score_bench_doubtful():
    a = {"type": "availability", "payload": {"status": "d"}}
    assert score_alert(a, in_xi=False, is_captain=False, before_deadline=True) == 70


def test_score_dgw_xi_pre_deadline():
    a = {"type": "dgw", "payload": {}}
    assert score_alert(a, in_xi=True, is_captain=False, before_deadline=True) == 65


def test_score_bgw_bench_post_deadline():
    a = {"type": "bgw", "payload": {}}
    assert score_alert(a, in_xi=False, is_captain=False, before_deadline=False) == 45


_PICKS = [
    # player_id, web_name, status, chance, news, multiplier, is_captain, is_vice, team_id
    {"player_id": 1, "web_name": "Salah", "status": "a", "chance_of_playing_next_round": None,
     "news": "", "multiplier": 2, "is_captain": True, "is_vice": False, "team_id": 10},
    {"player_id": 2, "web_name": "Isak", "status": "i", "chance_of_playing_next_round": 0,
     "news": "Knee injury - expected back 20 Oct", "multiplier": 1, "is_captain": False,
     "is_vice": False, "team_id": 11},
    {"player_id": 3, "web_name": "Gordon", "status": "a", "chance_of_playing_next_round": 75,
     "news": "Knock", "multiplier": 0, "is_captain": False, "is_vice": False, "team_id": 11},
]


def test_availability_alerts_only_flags_non_available():
    out = availability_alerts(_PICKS, gameweek_id=9)
    keys = {a["dedup_key"]: a for a in out}
    assert set(keys) == {"avail:2:i:0", "avail:3:a:75"}          # player 1 is fine -> no alert
    isak = keys["avail:2:i:0"]
    assert isak["type"] == "availability"
    assert isak["player_id"] == 2
    assert isak["gameweek_id"] == 9
    assert "Knee injury" in isak["body"]
    assert isak["payload"]["status"] == "i" and isak["payload"]["in_xi"] is True
    assert keys["avail:3:a:75"]["payload"]["in_xi"] is False


def test_dgw_bgw_alerts_from_owned_teams_and_fixture_counts():
    owned_team_ids = {10, 11}
    fixture_counts = {10: 2, 11: 0, 12: 2}   # 12 not owned -> ignored
    names_by_team = {10: ["Salah"], 11: ["Isak", "Gordon"]}
    out = {a["dedup_key"]: a for a in dgw_bgw_alerts(
        owned_team_ids, fixture_counts, names_by_team, gameweek_id=9)}
    assert set(out) == {"dgw:10:9", "bgw:11:9"}
    assert out["dgw:10:9"]["type"] == "dgw"
    assert out["bgw:11:9"]["type"] == "bgw"
    assert "Isak" in out["bgw:11:9"]["body"] and "Gordon" in out["bgw:11:9"]["body"]
    assert out["bgw:11:9"]["payload"]["player_names"] == ["Isak", "Gordon"]
```

Run: `python -m pytest packages/alerts/tests/test_alerts.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: implement `packages/alerts/src/fplguru_alerts/__init__.py`**
```python
"""Pure alert generation + priority scoring — no DB, no network."""
from __future__ import annotations

from typing import Any

__all__ = ["score_alert", "availability_alerts", "dgw_bgw_alerts"]

_BASE = {"availability": 60, "bgw": 45, "dgw": 40}
_HARD_OUT = {"i", "s", "u"}

_STATUS_LABEL = {
    "a": "available", "d": "doubtful", "i": "injured",
    "s": "suspended", "u": "unavailable", "n": "not in squad",
}


def score_alert(alert: dict[str, Any], *, in_xi: bool, is_captain: bool,
                before_deadline: bool) -> int:
    score = _BASE.get(alert["type"], 20)
    if is_captain:
        score += 25
    elif in_xi:
        score += 15
    if alert["type"] == "availability" and alert.get("payload", {}).get("status") in _HARD_OUT:
        score += 15
    if before_deadline:
        score += 10
    return max(0, min(100, score))


def availability_alerts(picks: list[dict[str, Any]], *, gameweek_id: int) -> list[dict]:
    out: list[dict] = []
    for p in picks:
        status = p.get("status", "a")
        chance = p.get("chance_of_playing_next_round")
        if status == "a" and (chance is None or chance >= 100):
            continue
        chance_key = "na" if chance is None else str(chance)
        news = (p.get("news") or "").strip()
        label = _STATUS_LABEL.get(status, status)
        detail = news or (
            f"Chance of playing next round: {chance}%." if chance is not None
            else "Status changed."
        )
        out.append({
            "type": "availability",
            "dedup_key": f"avail:{p['player_id']}:{status}:{chance_key}",
            "gameweek_id": gameweek_id,
            "player_id": p["player_id"],
            "title": f"{p['web_name']}: {label}",
            "body": detail,
            "payload": {
                "status": status,
                "chance": chance,
                "news": news,
                "in_xi": p.get("multiplier", 0) > 0,
                "is_captain": bool(p.get("is_captain")),
                "is_vice": bool(p.get("is_vice")),
            },
        })
    return out


def dgw_bgw_alerts(owned_team_ids: set[int], fixture_counts: dict[int, int],
                   names_by_team: dict[int, list[str]], *, gameweek_id: int) -> list[dict]:
    out: list[dict] = []
    for team_id in sorted(owned_team_ids):
        n = fixture_counts.get(team_id, 0)   # absent = no fixture that GW = blank
        names = names_by_team.get(team_id, [])
        if n == 0:
            kind, label = "bgw", "Blank gameweek"
        elif n >= 2:
            kind, label = "dgw", "Double gameweek"
        else:
            continue
        who = ", ".join(names) if names else "your player(s)"
        out.append({
            "type": kind,
            "dedup_key": f"{kind}:{team_id}:{gameweek_id}",
            "gameweek_id": gameweek_id,
            "player_id": None,
            "title": f"{label} — GW{gameweek_id}",
            "body": f"{label} for {who} ({n} fixture{'s' if n != 1 else ''}).",
            "payload": {"team_id": team_id, "fixtures": n, "player_names": names},
        })
    return out
```

- [ ] **Step 4:** `python -m pytest packages/alerts/tests/test_alerts.py -q` → **6 passed**.

- [ ] **Step 5: full verification + commit** — `python -m pytest -q -W error` → **115 passed** (109 + 6). `ruff` clean, `alembic check` clean.
  `feat(alerts): fplguru-alerts — priority score + availability / DGW-BGW generators`

---

## Task 3: `alerts` table + `linked_teams.alert_cap` + `0005` migration

**Files:**
- Modify: `packages/core/src/fplguru_core/models.py`, `packages/core/tests/test_models.py`
- Create: `alembic/versions/0005_alerts.py`, `packages/core/tests/test_alert_model.py`

- [ ] **Step 1: failing test** — `packages/core/tests/test_alert_model.py`:
```python
from fplguru_core.models import Alert, Base, LinkedTeam


def test_alert_table_and_dedup_uniqueness():
    assert "alerts" in Base.metadata.tables
    uqs = {
        tuple(sorted(c.name for c in con.columns))
        for con in Alert.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    }
    assert ("dedup_key", "linked_team_id") in uqs


def test_linked_team_has_alert_cap():
    col = LinkedTeam.__table__.c.alert_cap
    assert col.nullable is True
```

Add `"alerts"` to `packages/core/tests/test_models.py::test_expected_tables_registered`.

Run → FAIL (`ImportError: Alert`).

- [ ] **Step 2: models** — in `class LinkedTeam`, after `last_synced_at`:
```python
    alert_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = uncapped
```
Add after `class EntryPick` (keep entry-cluster ordering: linked_teams → entry_gw_history → entry_picks → alerts):
```python
class Alert(_TimestampMixin, Base):
    """A ranked, de-duplicated notification for one linked team."""
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("linked_team_id", "dedup_key",
                         name="uq_alerts_linked_team_id_dedup_key"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    linked_team_id: Mapped[int] = mapped_column(ForeignKey("linked_teams.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    type: Mapped[str] = mapped_column(String(24))              # availability | dgw | bgw
    dedup_key: Mapped[str] = mapped_column(String(128))
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(String, default="", server_default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 3: migration `alembic/versions/0005_alerts.py`** (`revision = '0005'`, `down_revision = '0004'`):
```python
def upgrade() -> None:
    op.create_table(
        'alerts',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('linked_team_id', sa.BigInteger(), nullable=False),
        sa.Column('gameweek_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=24), nullable=False),
        sa.Column('dedup_key', sa.String(length=128), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('body', sa.String(), server_default='', nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('suppressed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['gameweek_id'], ['gameweeks.id'],
                                name=op.f('fk_alerts_gameweek_id_gameweeks')),
        sa.ForeignKeyConstraint(['linked_team_id'], ['linked_teams.id'],
                                name=op.f('fk_alerts_linked_team_id_linked_teams')),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'],
                                name=op.f('fk_alerts_player_id_players')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_alerts')),
        sa.UniqueConstraint('linked_team_id', 'dedup_key',
                            name='uq_alerts_linked_team_id_dedup_key'),
    )
    op.create_index(op.f('ix_alerts_gameweek_id'), 'alerts', ['gameweek_id'], unique=False)
    op.create_index(op.f('ix_alerts_linked_team_id'), 'alerts', ['linked_team_id'], unique=False)
    op.add_column('linked_teams', sa.Column('alert_cap', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('linked_teams', 'alert_cap')
    op.drop_index(op.f('ix_alerts_linked_team_id'), table_name='alerts')
    op.drop_index(op.f('ix_alerts_gameweek_id'), table_name='alerts')
    op.drop_table('alerts')
```
Use `0003_entry_tables.py` as the exact style template for the header/imports.

- [ ] **Step 4:** `python -m alembic upgrade head` then `python -m alembic check` → `No new upgrade operations detected.` (If drift: usual causes are the `JSON` column default and the bool `server_default` — the model uses `default=dict` (Python-side, no server default) and `server_default="false"`; the migration must match: no `server_default` on `payload`, `sa.text('false')` on `suppressed`.)

- [ ] **Step 5:** `python -m pytest packages/core -q` → pass. `python -m pytest -q -W error` → **117 passed** (115 + 2). `ruff` clean, `alembic check` clean.
  `feat(core): alerts table + linked_teams.alert_cap (0005)`

---

## Task 4: worker `generate_alerts` task

**Files:**
- Modify: `services/worker/src/fplguru_worker/tasks.py`, `services/worker/src/fplguru_worker/app.py`, `services/worker/tests/test_beat_schedule.py`
- Create: `services/worker/tests/test_generate_alerts.py`

- [ ] **Step 1: failing test** — `services/worker/tests/test_generate_alerts.py`:
```python
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from fplguru_core.models import (
    Alert, EntryPick, Fixture, Gameweek, LinkedTeam, Player, Team,
)
from fplguru_worker import tasks


async def _seed(db_session, *, alert_cap=None):
    db_session.add_all([
        Team(id=10, name="Liverpool", short_name="LIV"),
        Team(id=11, name="Newcastle", short_name="NEW"),
        Team(id=12, name="Everton", short_name="EVE"),
    ])
    # current GW deadline in the future -> before_deadline = True
    db_session.add(Gameweek(id=9, name="GW9",
                            deadline_time=datetime.now(UTC) + timedelta(days=1),
                            is_current=True))
    await db_session.commit()
    db_session.add_all([
        Player(id=1, team_id=10, first_name="M", second_name="Salah", web_name="Salah",
               position="MID", now_cost=130, status="a"),
        Player(id=2, team_id=11, first_name="A", second_name="Isak", web_name="Isak",
               position="FWD", now_cost=100, status="i", chance_of_playing_next_round=0,
               news="Knee - out"),
        Player(id=3, team_id=11, first_name="A", second_name="Gordon", web_name="Gordon",
               position="MID", now_cost=75, status="a", chance_of_playing_next_round=75,
               news="Knock"),
    ])
    lt = LinkedTeam(id=1, fpl_entry_id=555, manager_name="Sam", alert_cap=alert_cap)
    db_session.add(lt)
    await db_session.commit()
    db_session.add_all([
        EntryPick(linked_team_id=1, gameweek_id=9, player_id=1, slot=1, multiplier=2,
                  is_captain=True, is_vice=False),
        EntryPick(linked_team_id=1, gameweek_id=9, player_id=2, slot=2, multiplier=1),
        EntryPick(linked_team_id=1, gameweek_id=9, player_id=3, slot=12, multiplier=0),
    ])
    # GW9 fixtures: Liverpool has 2 (DGW), Newcastle has 0 (BGW)
    db_session.add_all([
        Fixture(id=901, gameweek_id=9, home_team_id=10, away_team_id=12,
                home_difficulty=3, away_difficulty=3),
        Fixture(id=902, gameweek_id=9, home_team_id=12, away_team_id=10,
                home_difficulty=3, away_difficulty=3),
    ])
    await db_session.commit()


async def test_generate_alerts_creates_ranked_rows(db_session):
    await _seed(db_session)
    await tasks._generate_alerts()

    rows = {a.dedup_key: a for a in (await db_session.execute(select(Alert))).scalars()}
    # Isak (captain? no — Salah is captain; Isak in XI, hard out) + Gordon (bench doubtful)
    # + DGW Liverpool + BGW Newcastle
    assert set(rows) == {"avail:2:i:0", "avail:3:a:75", "dgw:10:9", "bgw:11:9"}
    assert rows["avail:2:i:0"].priority == 100                    # 60+15+15+10, clamped
    assert rows["avail:3:a:75"].priority == 60 + 10               # bench doubtful, pre-deadline
    assert rows["dgw:10:9"].priority == 40 + 25 + 10              # Salah is captain on Liverpool
    assert rows["bgw:11:9"].priority == 45 + 15 + 10             # Isak (XI) on Newcastle
    assert all(a.suppressed is False for a in rows.values())
    assert rows["avail:2:i:0"].linked_team_id == 1


async def test_generate_alerts_is_idempotent(db_session):
    await _seed(db_session)
    await tasks._generate_alerts()
    await tasks._generate_alerts()
    n = len((await db_session.execute(select(Alert))).scalars().all())
    assert n == 4


async def test_generate_alerts_applies_cap(db_session):
    await _seed(db_session, alert_cap=2)
    await tasks._generate_alerts()
    visible = (await db_session.execute(
        select(Alert).where(Alert.suppressed.is_(False)).order_by(Alert.priority.desc())
    )).scalars().all()
    assert len(visible) == 2
    assert [a.dedup_key for a in visible] == ["avail:2:i:0", "dgw:10:9"]
    suppressed = (await db_session.execute(
        select(Alert).where(Alert.suppressed.is_(True))
    )).scalars().all()
    assert {a.dedup_key for a in suppressed} == {"avail:3:a:75", "bgw:11:9"}
```

Run: `python -m pytest services/worker/tests/test_generate_alerts.py -q` → FAIL (`AttributeError: _generate_alerts`).

- [ ] **Step 2: implement in `services/worker/src/fplguru_worker/tasks.py`**

Extend the `fplguru_core.models` import with `Alert`, `EntryPick`; add `from fplguru_alerts import availability_alerts, dgw_bgw_alerts, score_alert` (alphabetical: after `fplguru_ingest`... actually `fplguru_alerts` sorts before `fplguru_core` — place it first in the first-party group). Add the helper + task after `_poll_live` / `poll_live`:
```python
async def _upsert_alerts(session, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(Alert).values(rows)
    update_cols = {
        c: stmt.excluded[c]
        for c in rows[0]
        if c not in ("linked_team_id", "dedup_key", "seen_at")
    }
    update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(
        index_elements=["linked_team_id", "dedup_key"], set_=update_cols
    )
    await session.execute(stmt)


async def _generate_alerts() -> None:
    started = datetime.now(UTC)
    try:
        async with get_sessionmaker()() as session, session.begin():
            gw = (
                await session.execute(select(Gameweek).where(Gameweek.is_current))
            ).scalar_one_or_none()
            if gw is None:
                await _record(session, "alerts", "ok", started, "no current gameweek")
                return
            before_deadline = gw.deadline_time > datetime.now(UTC)

            teams = (await session.execute(select(LinkedTeam))).scalars().all()
            fx_counts: dict[int, int] = {}
            for f in (await session.execute(
                select(Fixture).where(Fixture.gameweek_id == gw.id)
            )).scalars().all():
                fx_counts[f.home_team_id] = fx_counts.get(f.home_team_id, 0) + 1
                fx_counts[f.away_team_id] = fx_counts.get(f.away_team_id, 0) + 1

            total = 0
            for lt in teams:
                pick_gw = (await session.execute(
                    select(func.max(EntryPick.gameweek_id))
                    .where(EntryPick.linked_team_id == lt.id)
                )).scalar()
                if pick_gw is None:
                    continue
                picked = (await session.execute(
                    select(EntryPick, Player).join(Player, Player.id == EntryPick.player_id)
                    .where(EntryPick.linked_team_id == lt.id,
                           EntryPick.gameweek_id == pick_gw)
                )).all()
                picks = [{
                    "player_id": pl.id, "web_name": pl.web_name, "status": pl.status,
                    "chance_of_playing_next_round": pl.chance_of_playing_next_round,
                    "news": pl.news, "multiplier": ep.multiplier,
                    "is_captain": ep.is_captain, "is_vice": ep.is_vice, "team_id": pl.team_id,
                } for ep, pl in picked]
                by_player = {p["player_id"]: p for p in picks}
                owned_teams = {p["team_id"] for p in picks}
                names_by_team: dict[int, list[str]] = {}
                for p in picks:
                    names_by_team.setdefault(p["team_id"], []).append(p["web_name"])

                generated = availability_alerts(picks, gameweek_id=gw.id)
                if sum(fx_counts.values()) > 0:  # this GW's fixtures are loaded
                    generated += dgw_bgw_alerts(
                        owned_teams, fx_counts, names_by_team, gameweek_id=gw.id
                    )
                rows = []
                for a in generated:
                    owner = by_player.get(a["player_id"]) if a["player_id"] else None
                    in_xi = bool(owner and owner["multiplier"] > 0)
                    is_cap = bool(owner and owner["is_captain"])
                    if a["type"] in ("dgw", "bgw"):
                        team_names = a["payload"].get("player_names", [])
                        in_xi = any(
                            by_player[p]["multiplier"] > 0
                            for p in by_player
                            if by_player[p]["web_name"] in team_names
                        )
                        is_cap = any(
                            by_player[p]["is_captain"]
                            for p in by_player
                            if by_player[p]["web_name"] in team_names
                        )
                    rows.append({
                        "linked_team_id": lt.id,
                        "gameweek_id": a["gameweek_id"],
                        "type": a["type"],
                        "dedup_key": a["dedup_key"],
                        "player_id": a["player_id"],
                        "title": a["title"],
                        "body": a["body"],
                        "payload": a["payload"],
                        "priority": score_alert(
                            a, in_xi=in_xi, is_captain=is_cap,
                            before_deadline=before_deadline,
                        ),
                        "suppressed": False,
                    })
                await _upsert_alerts(session, rows)
                total += len(rows)

                # cap application: rank this GW's alerts, suppress the tail
                gw_alerts = (await session.execute(
                    select(Alert)
                    .where(Alert.linked_team_id == lt.id, Alert.gameweek_id == gw.id)
                    .order_by(Alert.priority.desc(), Alert.id)
                )).scalars().all()
                for i, row in enumerate(gw_alerts):
                    row.suppressed = lt.alert_cap is not None and i >= lt.alert_cap

            await _record(session, "alerts", "ok", started, f"{total} alerts over {len(teams)} teams")
        logger.info("alerts generated: %d rows", total)
    except Exception as exc:
        await _log_error("alerts", started, exc)
        raise


@celery_app.task(name="generate_alerts", bind=True, max_retries=2, default_retry_delay=60)
def generate_alerts(self) -> None:
    try:
        asyncio.run(_run_and_dispose(_generate_alerts))
    except Exception as exc:
        raise self.retry(exc=exc) from exc
```
Note: `_upsert_alerts` deliberately does **not** overwrite `priority`/`suppressed` on conflict? — it must overwrite `priority` (recompute each run) but never `seen_at`. It also must not reset `suppressed` to the row value here because the cap pass rewrites it right after; that's fine because the cap pass runs in the same transaction after the upsert. Keep `priority` and `suppressed` in `update_cols` (only `seen_at` excluded, plus the conflict keys).

- [ ] **Step 3: Beat + assertion** — in `app.py` `beat_schedule` add `"generate-alerts": {"task": "generate_alerts", "schedule": 1800.0}` (30 min). In `test_beat_schedule.py` add `assert sched["generate-alerts"]["task"] == "generate_alerts"`.

- [ ] **Step 4:** `python -m pytest services/worker/tests/test_generate_alerts.py services/worker/tests/test_beat_schedule.py -q` → **4 passed**. `python -m pytest -q -W error` → **121 passed** (117 + 4). `ruff` clean, `alembic check` clean.
  `feat(worker): generate_alerts task — per-team ranked alert feed with cap`

---

## Task 5: API — feed, mark-seen, settings

**Files:**
- Modify: `services/api/src/fplguru_api/main.py`, `services/api/pyproject.toml`
- Create: `services/api/tests/test_alerts_api.py`

- [ ] **Step 1: deps** — add `"fplguru-alerts"` to `services/api/pyproject.toml` `dependencies` (even though the API doesn't import it directly yet — keeps the service closure honest; skip if a reviewer objects). Actually **only add it if the API imports it**; it does not, so **leave `pyproject.toml` unchanged** and delete this step. (Kept here so the implementer doesn't add a phantom dep.)

- [ ] **Step 2: failing test** — `services/api/tests/test_alerts_api.py`:
```python
from datetime import UTC, datetime, timedelta

from fplguru_core.models import Alert, Gameweek, LinkedTeam


async def _seed(db_session):
    db_session.add(Gameweek(id=9, name="GW9",
                            deadline_time=datetime.now(UTC) + timedelta(days=1),
                            is_current=True))
    db_session.add(LinkedTeam(id=1, fpl_entry_id=555, manager_name="Sam"))
    await db_session.commit()
    db_session.add_all([
        Alert(linked_team_id=1, gameweek_id=9, type="availability", dedup_key="a1",
              player_id=None, priority=90, title="Isak: injured", body="Knee", payload={},
              suppressed=False),
        Alert(linked_team_id=1, gameweek_id=9, type="dgw", dedup_key="a2",
              player_id=None, priority=55, title="DGW", body="x", payload={},
              suppressed=False),
        Alert(linked_team_id=1, gameweek_id=9, type="bgw", dedup_key="a3",
              player_id=None, priority=20, title="BGW", body="y", payload={},
              suppressed=True),
    ])
    await db_session.commit()


async def test_alert_feed_default_hides_suppressed_and_sorts_by_priority(client, db_session):
    await _seed(db_session)
    body = (await client.get("/entries/555/alerts")).json()
    assert [a["title"] for a in body["alerts"]] == ["Isak: injured", "DGW"]
    assert body["unseen"] == 2
    assert body["alerts"][0]["seen"] is False


async def test_alert_feed_include_suppressed(client, db_session):
    await _seed(db_session)
    body = (await client.get("/entries/555/alerts?include_suppressed=true")).json()
    assert len(body["alerts"]) == 3


async def test_mark_seen_all(client, db_session):
    await _seed(db_session)
    r = await client.post("/entries/555/alerts/seen", json={})
    assert r.json()["marked"] == 2
    body = (await client.get("/entries/555/alerts")).json()
    assert body["unseen"] == 0
    assert body["alerts"][0]["seen"] is True


async def test_mark_seen_specific_ids(client, db_session):
    await _seed(db_session)
    first = (await client.get("/entries/555/alerts")).json()["alerts"][0]["id"]
    r = await client.post("/entries/555/alerts/seen", json={"ids": [first]})
    assert r.json()["marked"] == 1


async def test_patch_settings_alert_cap(client, db_session):
    await _seed(db_session)
    r = await client.patch("/entries/555/settings", json={"alert_cap": 5})
    assert r.status_code == 200 and r.json()["alert_cap"] == 5
    r2 = await client.patch("/entries/555/settings", json={"alert_cap": None})
    assert r2.json()["alert_cap"] is None


async def test_alerts_unknown_entry_404(client, db_session):
    assert (await client.get("/entries/999/alerts")).status_code == 404
```

Run → FAIL (404s).

- [ ] **Step 3: implement in `main.py`** — add `Alert` to the `fplguru_core.models` import. Add `from pydantic import BaseModel` near the fastapi import if not present (check — P1a/P1c may already use pydantic models; if not, add it). Then:
```python
class _SeenBody(BaseModel):
    ids: list[int] | None = None


class _SettingsBody(BaseModel):
    alert_cap: int | None = None


def _alert_json(a: Alert) -> dict:
    return {
        "id": a.id, "type": a.type, "gameweek_id": a.gameweek_id,
        "player_id": a.player_id, "priority": a.priority, "title": a.title,
        "body": a.body, "payload": a.payload, "suppressed": a.suppressed,
        "seen": a.seen_at is not None,
        "created_at": a.updated_at.isoformat(),
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
    async with db.begin():
        q = select(Alert).where(Alert.linked_team_id == lt.id, Alert.seen_at.is_(None))
        if body.ids:
            q = q.where(Alert.id.in_(body.ids))
        rows = (await db.execute(q)).scalars().all()
        now = func.now()
        for a in rows:
            a.seen_at = now
        return {"marked": len(rows)}


@app.patch("/entries/{entry_id}/settings")
async def patch_entry_settings(
    entry_id: int, body: _SettingsBody, db: AsyncSession = Depends(get_db)
) -> dict:
    lt = await _linked_or_404(db, entry_id)
    async with db.begin():
        lt.alert_cap = body.alert_cap
    return {"fpl_entry_id": lt.fpl_entry_id, "alert_cap": lt.alert_cap}
```
Note on `mark_alerts_seen`: assigning `func.now()` to an ORM attribute then committing works (SQLAlchemy renders it as a SQL expression on UPDATE). If a reviewer prefers, use `datetime.now(UTC)` — add `from datetime import UTC, datetime` (check imports).

- [ ] **Step 4:** `python -m pytest services/api/tests/test_alerts_api.py -q` → **7 passed**. `python -m pytest -q -W error` → **128 passed** (121 + 7). `ruff` clean, `alembic check` clean.
  `feat(api): alert feed, mark-seen, and alert_cap settings for linked teams`

---

## Task 6: web — alert API client + types

**Files:**
- Modify: `apps/web/src/lib/api.ts`
- Create: `apps/web/src/lib/api.alerts.test.ts`

- [ ] **Step 1: failing test** — `apps/web/src/lib/api.alerts.test.ts`:
```ts
import { describe, expect, it, vi } from "vitest";

import { getAlerts, markAlertsSeen } from "./api";

describe("alerts api", () => {
  it("getAlerts hits the feed endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ alerts: [], unseen: 0 }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;
    const r = await getAlerts("http://api.test", 7);
    expect(r.unseen).toBe(0);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/entries/7/alerts");
  });

  it("markAlertsSeen posts ids", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ marked: 1 }) });
    global.fetch = fetchMock as unknown as typeof fetch;
    await markAlertsSeen("http://api.test", 7, [3]);
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ ids: [3] });
  });
});
```

- [ ] **Step 2: implement** — append to `apps/web/src/lib/api.ts`:
```ts
export type Alert = {
  id: number;
  type: string;
  gameweek_id: number;
  player_id: number | null;
  priority: number;
  title: string;
  body: string;
  payload: Record<string, unknown>;
  suppressed: boolean;
  seen: boolean;
  created_at: string;
};
export type AlertFeed = { alerts: Alert[]; unseen: number };

export function getAlerts(base: string, entryId: number, includeSuppressed = false) {
  const q = includeSuppressed ? "?include_suppressed=true" : "";
  return fetch(`${base}/entries/${entryId}/alerts${q}`, { cache: "no-store" }).then(
    asJson<AlertFeed>,
  );
}

export function markAlertsSeen(base: string, entryId: number, ids?: number[]) {
  return fetch(`${base}/entries/${entryId}/alerts/seen`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(ids ? { ids } : {}),
  }).then(asJson<{ marked: number }>);
}

export function updateEntrySettings(base: string, entryId: number, alertCap: number | null) {
  return fetch(`${base}/entries/${entryId}/settings`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ alert_cap: alertCap }),
  }).then(asJson<{ fpl_entry_id: number; alert_cap: number | null }>);
}
```

- [ ] **Step 3:** `./node_modules/.bin/vitest run` → 7 passed (5 + 2).
  `feat(web): alert feed / mark-seen / settings API clients`

---

## Task 7: web — `/alerts` page + nav badge

**Files:**
- Create: `apps/web/src/app/alerts/page.tsx`, `apps/web/src/app/alerts/AlertFeed.tsx`, `apps/web/src/app/NavAlerts.tsx`
- Modify: `apps/web/src/app/layout.tsx`

- [ ] **Step 1: `apps/web/src/app/alerts/page.tsx`**
```tsx
import { AlertFeed } from "./AlertFeed";

export default function AlertsPage() {
  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">Alerts</h1>
      <AlertFeed />
    </main>
  );
}
```

- [ ] **Step 2: `apps/web/src/app/alerts/AlertFeed.tsx`** (client)
```tsx
"use client";

import { useCallback, useEffect, useState } from "react";

import { type Alert, getAlerts, markAlertsSeen, updateEntrySettings } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const TONE: Record<string, string> = {
  availability: "border-red-300",
  bgw: "border-amber-300",
  dgw: "border-emerald-300",
};

export function AlertFeed() {
  const [entryId, setEntryId] = useState<number | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [cap, setCap] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => setEntryId(getStoredEntryId()), []);

  const load = useCallback(() => {
    if (entryId == null) return;
    getAlerts(API, entryId)
      .then((f) => {
        setAlerts(f.alerts);
        setErr(null);
      })
      .catch(() => setErr("Could not load alerts."));
  }, [entryId]);

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  if (entryId == null)
    return <p className="mt-4 text-sm text-gray-500">Link your team first (Squad tab).</p>;

  return (
    <>
      <div className="mt-2 flex items-center gap-3 text-sm">
        <button
          className="rounded border px-2 py-1"
          onClick={() => markAlertsSeen(API, entryId).then(load)}
        >
          Mark all read
        </button>
        <label className="flex items-center gap-1 text-gray-500">
          Max alerts
          <input
            className="w-16 rounded border px-1 py-0.5"
            value={cap}
            onChange={(e) => setCap(e.target.value.replace(/[^0-9]/g, ""))}
            placeholder="∞"
          />
          <button
            className="rounded border px-2 py-0.5"
            onClick={() =>
              updateEntrySettings(API, entryId, cap === "" ? null : Number(cap)).then(load)
            }
          >
            Save
          </button>
        </label>
      </div>
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
      <ul className="mt-4 space-y-2">
        {alerts.length === 0 && (
          <li className="text-sm text-gray-500">No alerts right now.</li>
        )}
        {alerts.map((a) => (
          <li
            key={a.id}
            className={`rounded border-l-4 bg-white/5 px-3 py-2 ${TONE[a.type] ?? "border-gray-300"} ${
              a.seen ? "opacity-60" : ""
            }`}
          >
            <div className="flex justify-between text-sm font-medium">
              <span>{a.title}</span>
              <span className="text-gray-400">p{a.priority}</span>
            </div>
            <p className="text-sm text-gray-500">{a.body}</p>
          </li>
        ))}
      </ul>
    </>
  );
}
```

- [ ] **Step 3: `apps/web/src/app/NavAlerts.tsx`** (client island for the unseen badge)
```tsx
"use client";

import { useEffect, useState } from "react";

import { getAlerts } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function NavAlerts() {
  const [unseen, setUnseen] = useState(0);

  useEffect(() => {
    const id = getStoredEntryId();
    if (id == null) return;
    const tick = () =>
      getAlerts(API, id)
        .then((f) => setUnseen(f.unseen))
        .catch(() => undefined);
    tick();
    const t = setInterval(tick, 60000);
    return () => clearInterval(t);
  }, []);

  return (
    <a href="/alerts">
      Alerts
      {unseen > 0 && (
        <span className="ml-1 rounded-full bg-red-500 px-1.5 text-xs text-white">
          {unseen}
        </span>
      )}
    </a>
  );
}
```

- [ ] **Step 4: `apps/web/src/app/layout.tsx`** — add `import { NavAlerts } from "./NavAlerts";` and put `<NavAlerts />` in the `<nav>` after the `FDR` link (replace nothing else).

- [ ] **Step 5:** `./node_modules/.bin/vitest run` → 7 passed (unchanged). `./node_modules/.bin/next build` → success; route list shows `○ /alerts`.
  `feat(web): /alerts feed page + nav unseen badge`

---

## Task 8: docs

**Files:** Modify `README.md`, `docs/plans/2026-08-27-fplguru-master-build-plan.md`, `docs/RESUME-foundation.md`.

- [ ] **Step 1: `README.md`** — add `/entries/{id}/alerts` + `/entries/{id}/settings` to the API list; add an "Alerts" section:
```markdown
## Alerts

A `generate_alerts` worker task (Beat, 30 min) builds a ranked, de-duplicated feed
per linked team: player availability changes (`status` / `chance_of_playing`) and
blank/double gameweeks for teams you own. Priority score is documented in
[`docs/design/2026-08-27-alert-priority-ranking.md`](docs/design/2026-08-27-alert-priority-ranking.md).
`linked_teams.alert_cap` (default `NULL` = uncapped) suppresses the lowest-priority
alerts beyond the cap. Web Push delivery lands with the PWA work (P1h); today the
feed is in-app only.

    GET   /entries/{id}/alerts[?include_suppressed=true]
    POST  /entries/{id}/alerts/seen        {ids?: number[]}   # omit ids -> mark all
    PATCH /entries/{id}/settings           {alert_cap: number | null}
```

- [ ] **Step 2: master plan** — mark **P1e** ✅ (branch `feature/p1e-alerts`): design doc + `fplguru-alerts` pkg (score + availability / DGW-BGW generators); `alerts` table + `linked_teams.alert_cap` (`0005`); `generate_alerts` Beat task with cap application; `GET /entries/{id}/alerts`, `POST .../alerts/seen`, `PATCH .../settings`; `/alerts` web feed + nav badge. Note: `price_change` / `fdr_shift` generators and Web Push delivery deferred (P1h owns push). Decrement the "Remaining sub-plans" count (15 → 14).

- [ ] **Step 3: `docs/RESUME-foundation.md`** — update the top status line and add a `## P1e — Alerts Engine` section (task table + commits + the deferred-generators / push-deferred notes), and update "Remaining unblocked Phase-1 path" to `P1f → P1h`.

- [ ] **Step 4: full verification** — `python -m pytest -q -W error` → **128 passed**; `ruff` clean; `alembic check` clean; web `vitest run` → 7 passed; `next build` → success.

- [ ] **Step 5: commit** — `docs: P1e Alerts Engine complete`

---

## Self-Review

**Spec coverage (master §3 P1e / PRD §4.3, §3):**
- Priority-ranking design doc first → Task 1 ✓
- Alert model → Task 3 (`alerts` table, `dedup_key` unique per team) ✓
- Generators: injury/availability from `chance_of_playing` / `news` → `availability_alerts` (Task 2); DGW/BGW → `dgw_bgw_alerts` (Task 2) ✓ · fixture-reminder → that's **P1f** (deadline reminders) · FDR-shift / price-change → **deferred**, documented ✓ (partial by design)
- In-app feed → `GET /entries/{id}/alerts` + `/alerts` page (Tasks 5, 7) ✓
- Web Push delivery → **deferred to P1h** (owns VAPID + subscriptions); alert rows are push-shaped (`title` / `body` / payload) ✓ (explicitly deferred)
- Cap + reset at deadline + drop-lowest-priority → `alert_cap` (nullable, default uncapped — no tier, no "upgrade" message per the scope override); cap pass suppresses lowest-priority; the cap is re-evaluated every run and `score_alert` adds a pre-deadline bump so ordering shifts appropriately across the deadline (Tasks 2, 4) ✓

**Type/name consistency:**
- `score_alert(alert, *, in_xi, is_captain, before_deadline) -> int` — Task 2 def == Task 4 call ✓
- generator alert dict keys `type, dedup_key, gameweek_id, player_id, title, body, payload` → mapped to `Alert` columns + `linked_team_id` + `priority` + `suppressed` in Task 4's `rows` build ✓
- `Alert` unique key `(linked_team_id, dedup_key)` == `_upsert_alerts` `index_elements` == migration `UniqueConstraint` ✓
- feed JSON (`_alert_json`) == web `Alert` type (`id,type,gameweek_id,player_id,priority,title,body,payload,suppressed,seen,created_at`) ✓
- `alert_cap` nullable int: model, migration `add_column` (nullable, no default), `PATCH /settings` body, web control ✓

**Migration drift:** `0005` adds one table + one nullable column; Task 3 Step 4 runs `alembic check`; `test_expected_tables_registered` updated same task; `payload` JSON has no server default (model `default=dict`), `suppressed`/`body` server defaults match the model.

**Placeholder scan:** none — all code inline. (Task 5 Step 1 is intentionally a "do nothing / delete this step" instruction so the implementer doesn't add a phantom `pyproject.toml` dep.)

---

## Execution Handoff

Branch `feature/p1e-alerts` off `main`. Subagent-driven, order 1 → 8. Task 2 (score + generators) and Task 4 (worker orchestration + cap) get a full spec + code-quality review; Tasks 3, 5 spec-check + quality-check; Tasks 1, 6, 7, 8 spec-check. After Task 8: whole-branch review, then PR `feature/p1e-alerts` → `main`, watch CI, squash-merge.

### Deferred follow-ups
- `price_change` generator — needs a `player_cost_history` snapshot table (or a `now_cost` column diff captured each bootstrap sync).
- `fdr_shift` generator — needs per-GW FDR snapshots persisted (reuse `fplguru_fdr`).
- Web Push delivery sink + VAPID + `push_subscriptions` — **P1h**.
- Per-type mute preferences (`linked_teams` JSON column or a `alert_prefs` table).
- Alert retention/pruning (drop `seen` alerts older than N GWs).
