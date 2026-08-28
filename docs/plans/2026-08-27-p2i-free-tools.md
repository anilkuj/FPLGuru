# P2i — Free Tools Suite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Ship four self-contained analysis tools off data FPLGuru already has — **GW Trends**, **Template Analyser**, **DGW/BGW Calendar**, **Overpowered XI** — behind a `/tools` hub.

**Architecture:** A new pure package `fplguru-tools` holds the four computations (plain dicts in, plain dicts out). `normalize_players` gains four transfer/price/form fields (small `players` schema add, migration `0009`). The read API exposes one endpoint per tool plus a per-entry template diff. The web `/tools` route is a tabbed client view.

**Tech Stack:** SQLAlchemy + Alembic (`0009`), a pure `fplguru-tools` package, FastAPI, Next.js 16, Vitest 4. No new data source. (The "xG/CS Snapshot" tool from the master plan is **deferred to P2a** — PitchAPI ingestion; until then FDR already covers scoring-vs-cleansheet difficulty.)

---

## Project context (read once)

Same monorepo / SAC toolchain / TDD / commit conventions as the recent plans — re-read the
"Project context" block in [`docs/plans/2026-08-27-p1e-alerts-engine.md`](2026-08-27-p1e-alerts-engine.md).
Branch: **`feature/p2i-free-tools`** off `main`.

P2i-specific facts:
- `packages/ingest/src/fplguru_ingest/fpl.py` `normalize_players` currently emits
  `id, team_id, first_name, second_name, web_name, position, now_cost, status,
  chance_of_playing_next_round, news, selected_by_percent, total_points`. FPL `elements` also carry
  `transfers_in_event`, `transfers_out_event`, `cost_change_event` (tenths, this GW), `form` (str).
- `Player` model (`packages/core/src/fplguru_core/models.py`) — natural-key PK, `_TimestampMixin`.
  `selected_by_percent: Float`, `now_cost: Integer` (tenths), `position: String(3)` (GK/DEF/MID/FWD).
- `Fixture` has `gameweek_id` (nullable), `home_team_id`, `away_team_id`, `finished`, `started`.
- `PlayerGwPrediction` has `player_id, gameweek_id, horizon_gw, model_version, xp`; API constant
  `_MODEL_VERSION = "basic-v1"`. `GET /xp?horizon=` already sums xp per player over `horizon_gw <= horizon`.
- API `main.py`: `_linked_or_404`, `EntryPick`, `Team` imported. Tests: `client` + `db_session`.
- Web: `apps/web`, `src/lib/api.ts` `asJson<T>` (exported), pages = server shell + `"use client"` child,
  nav in `layout.tsx`. `src/lib/entry.ts` `getStoredEntryId()`.
- **Baseline:** repo-root `python -m pytest -q` → **156 passed**; web `vitest run` → **14 passed**.
  (Note a known intermittent local asyncpg flake on one worker DB test — re-run/isolate to confirm; CI Linux is unaffected.)

---

## File Structure

| File | Responsibility |
|---|---|
| `packages/tools/` (new pkg `fplguru-tools`) | `trends`, `template_xi`, `template_diff`, `gw_calendar`, `pick_overpowered_xi` — pure. |
| `packages/core/.../models.py` | `Player` gains `transfers_in_event`, `transfers_out_event`, `cost_change_event`, `form`. |
| `packages/ingest/.../fpl.py` | `normalize_players` emits the four new fields. |
| `alembic/versions/0009_player_trends.py` | the four columns. |
| `services/api/.../main.py` | `GET /trends`, `/template`, `/entries/{id}/template-diff`, `/calendar`, `/overpowered`. |
| `apps/web/src/lib/api.ts` | tool clients + types. |
| `apps/web/src/app/tools/page.tsx`, `tools/ToolsHub.tsx` | tabbed hub. |
| `apps/web/src/app/layout.tsx` | nav link `Tools`. |

---

## Task 1: `players` trend/price/form columns + `0009`

**Files:** `packages/core/.../models.py`, `packages/ingest/.../fpl.py`, `packages/ingest/tests/test_fpl_normalizers.py`, `packages/ingest/tests/fixtures/bootstrap_sample.json`, `packages/core/tests/test_models.py` *(only if it asserts Player columns — check; `test_expected_tables_registered` is unaffected, no new table)*, `alembic/versions/0009_player_trends.py`.

- [ ] **Step 1: failing test** — append to `packages/ingest/tests/test_fpl_normalizers.py`:
```python
def test_normalize_players_carries_trend_fields():
    row = normalize_players(BOOTSTRAP)[0]
    assert row["transfers_in_event"] == 150000
    assert row["transfers_out_event"] == 20000
    assert row["cost_change_event"] == 1
    assert row["form"] == 5.5
```
Add those keys to the **first** element of `packages/ingest/tests/fixtures/bootstrap_sample.json`
(`"transfers_in_event": 150000, "transfers_out_event": 20000, "cost_change_event": 1, "form": "5.5"`).
Also add a `test_player_model` assertion (new file `packages/core/tests/test_player_trends.py`):
```python
def test_player_has_trend_columns():
    from fplguru_core.models import Player
    cols = {c.name for c in Player.__table__.columns}
    assert {"transfers_in_event", "transfers_out_event", "cost_change_event", "form"} <= cols
```

- [ ] **Step 2: model** — in `class Player`, after `total_points`:
```python
    transfers_in_event: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    transfers_out_event: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_change_event: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # tenths
    form: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
```

- [ ] **Step 3: `normalize_players`** — add to the dict:
```python
            "transfers_in_event": el.get("transfers_in_event", 0),
            "transfers_out_event": el.get("transfers_out_event", 0),
            "cost_change_event": el.get("cost_change_event", 0),
            "form": float(el.get("form") or 0.0),
```

- [ ] **Step 4: migration `alembic/versions/0009_player_trends.py`** (`revision='0009'`, `down_revision='0008'`):
```python
def upgrade() -> None:
    op.add_column('players', sa.Column('transfers_in_event', sa.Integer(), nullable=False,
                                       server_default='0'))
    op.add_column('players', sa.Column('transfers_out_event', sa.Integer(), nullable=False,
                                       server_default='0'))
    op.add_column('players', sa.Column('cost_change_event', sa.Integer(), nullable=False,
                                       server_default='0'))
    op.add_column('players', sa.Column('form', sa.Float(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('players', 'form')
    op.drop_column('players', 'cost_change_event')
    op.drop_column('players', 'transfers_out_event')
    op.drop_column('players', 'transfers_in_event')
```

- [ ] **Step 5:** `python -m alembic upgrade head`; `python -m alembic check` → clean (match `server_default='0'` on `form` to the model's `server_default="0"`). `python -m pytest packages/core packages/ingest -q` → pass. `python -m pytest -q -W error` → **158 passed** (156 + 2). `ruff` clean.
  `feat(core): players transfer/price/form columns (0009)`

---

## Task 2: `fplguru-tools` package (pure)

**Files:** `packages/tools/pyproject.toml`, `packages/tools/src/fplguru_tools/__init__.py`, `packages/tools/tests/test_tools.py`; `requirements-dev.txt`, `pyproject.toml` (ruff isort).

- [ ] **Step 1: skeleton** like `packages/live/pyproject.toml` → `name = "fplguru-tools"`,
  `description = "Pure FPL analysis tools: trends, template XI, DGW/BGW calendar, overpowered XI."`,
  `packages = ["src/fplguru_tools"]`. Add `-e ./packages/tools` to `requirements-dev.txt`; add
  `"fplguru_tools"` to `known-first-party`. `pip install -r requirements-dev.txt`.

- [ ] **Step 2: failing test** — `packages/tools/tests/test_tools.py`:
```python
from fplguru_tools import (
    gw_calendar,
    pick_overpowered_xi,
    template_diff,
    template_xi,
    trends,
)


def _p(pid, pos, sel, tin=0, tout=0, dc=0, team=1, name=None):
    return {"player_id": pid, "web_name": name or f"P{pid}", "position": pos, "team_id": team,
            "selected_by_percent": sel, "transfers_in_event": tin, "transfers_out_event": tout,
            "cost_change_event": dc, "now_cost": 50}


def test_trends_ranks_each_bucket():
    ps = [
        _p(1, "MID", 40, tin=900, tout=10, dc=1),
        _p(2, "FWD", 30, tin=50, tout=800, dc=-1),
        _p(3, "DEF", 55, tin=100, tout=100, dc=0),
    ]
    out = trends(ps, limit=2)
    assert [x["player_id"] for x in out["transfers_in"]] == [1, 3]
    assert [x["player_id"] for x in out["transfers_out"]] == [2, 3]
    assert [x["player_id"] for x in out["price_risers"]] == [1]
    assert [x["player_id"] for x in out["price_fallers"]] == [2]
    assert [x["player_id"] for x in out["most_owned"]] == [3, 1]


def test_template_xi_picks_most_owned_valid_formation():
    ps = (
        [_p(100, "GK", 60)]
        + [_p(200 + i, "DEF", 50 - i) for i in range(6)]
        + [_p(300 + i, "MID", 40 - i) for i in range(6)]
        + [_p(400 + i, "FWD", 30 - i) for i in range(4)]
    )
    xi = template_xi(ps)
    assert xi["formation"] in {"3-4-3", "3-5-2", "4-4-2", "4-3-3", "4-5-1", "5-4-1", "5-3-2"}
    assert len([p for p in xi["xi"] if p["position"] == "GK"]) == 1
    assert len(xi["xi"]) == 11
    assert xi["xi"][0]["player_id"] == 100          # the GK
    # every defender chosen is more-owned than any defender left out
    picked_def = {p["player_id"] for p in xi["xi"] if p["position"] == "DEF"}
    assert 200 in picked_def


def test_template_diff_counts_overlap_and_differentials():
    tmpl = {"xi": [{"player_id": 1}, {"player_id": 2}, {"player_id": 3}]}
    picks = [{"player_id": 2}, {"player_id": 3}, {"player_id": 9}]
    d = template_diff(picks, tmpl)
    assert d["overlap"] == 2
    assert d["your_differentials"] == [9]
    assert d["template_only"] == [1]


def test_gw_calendar_flags_blanks_and_doubles():
    fixtures = [
        {"gameweek_id": 5, "home_team_id": 1, "away_team_id": 2},
        {"gameweek_id": 5, "home_team_id": 3, "away_team_id": 1},   # team 1 plays twice
        {"gameweek_id": 6, "home_team_id": 2, "away_team_id": 3},   # team 1 blank
    ]
    gws = [{"id": 5}, {"id": 6}]
    cal = {c["gameweek_id"]: c for c in gw_calendar(fixtures, gws, from_gw=5, to_gw=6, team_ids=[1, 2, 3])}
    assert cal[5]["doubles"] == [1]
    assert cal[5]["blanks"] == []
    assert cal[6]["blanks"] == [1]
    assert cal[6]["doubles"] == []


def test_pick_overpowered_xi_maximises_xp_within_a_valid_formation():
    ps = (
        [{"player_id": 1, "web_name": "GK", "position": "GK", "team_id": 1, "now_cost": 45, "xp": 5}]
        + [{"player_id": 10 + i, "web_name": f"D{i}", "position": "DEF", "team_id": 2,
            "now_cost": 45, "xp": 6 - i} for i in range(5)]
        + [{"player_id": 20 + i, "web_name": f"M{i}", "position": "MID", "team_id": 3,
            "now_cost": 60, "xp": 8 - i} for i in range(5)]
        + [{"player_id": 30 + i, "web_name": f"F{i}", "position": "FWD", "team_id": 4,
            "now_cost": 70, "xp": 9 - i} for i in range(3)]
    )
    xi = pick_overpowered_xi(ps)
    assert len(xi["xi"]) == 11
    assert xi["formation"].count("-") == 2
    # the single best forward must be in the XI
    assert 30 in {p["player_id"] for p in xi["xi"]}
    assert xi["total_xp"] == round(sum(p["xp"] for p in xi["xi"]), 2)
```

- [ ] **Step 3: implement `packages/tools/src/fplguru_tools/__init__.py`**
```python
"""Pure FPL analysis tools — no DB, no network."""
from __future__ import annotations

from typing import Any

__all__ = [
    "trends", "template_xi", "template_diff", "gw_calendar", "pick_overpowered_xi",
]

# valid outfield splits (DEF, MID, FWD); GK is always 1
_FORMATIONS = [(3, 4, 3), (3, 5, 2), (4, 4, 2), (4, 3, 3), (4, 5, 1), (5, 4, 1), (5, 3, 2)]
_POS_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}


def _brief(p: dict[str, Any], value_key: str) -> dict:
    return {"player_id": p["player_id"], "web_name": p["web_name"],
            "position": p["position"], "value": p[value_key]}


def trends(players: list[dict[str, Any]], *, limit: int = 10) -> dict:
    def top(key: str, *, reverse: bool = True, keep=lambda p: True):
        ranked = sorted((p for p in players if keep(p)),
                        key=lambda p: (p.get(key, 0), p["player_id"]), reverse=reverse)
        return [_brief(p, key) for p in ranked[:limit]]

    return {
        "transfers_in": top("transfers_in_event"),
        "transfers_out": top("transfers_out_event"),
        "price_risers": top("cost_change_event", keep=lambda p: p.get("cost_change_event", 0) > 0),
        "price_fallers": [
            _brief(p, "cost_change_event")
            for p in sorted((x for x in players if x.get("cost_change_event", 0) < 0),
                            key=lambda p: (p["cost_change_event"], p["player_id"]))[:limit]
        ],
        "most_owned": top("selected_by_percent"),
    }


def _fill(players: list[dict], key: str) -> tuple[list[dict], float]:
    """Best XI + score for the formation that maximises the summed `key`."""
    by_pos: dict[str, list[dict]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for p in players:
        by_pos.get(p["position"], []).append(p)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda p: (p.get(key, 0), -p["player_id"]), reverse=True)

    best: tuple[list[dict], float] | None = None
    gk = by_pos["GK"][:1]
    for d, m, f in _FORMATIONS:
        if len(by_pos["DEF"]) < d or len(by_pos["MID"]) < m or len(by_pos["FWD"]) < f or not gk:
            continue
        xi = gk + by_pos["DEF"][:d] + by_pos["MID"][:m] + by_pos["FWD"][:f]
        score = sum(p.get(key, 0) for p in xi)
        if best is None or score > best[1]:
            best = (xi, score)
    if best is None:
        return [], 0.0
    return best[0], best[1]


def _formation_str(xi: list[dict]) -> str:
    n = {"DEF": 0, "MID": 0, "FWD": 0}
    for p in xi:
        if p["position"] in n:
            n[p["position"]] += 1
    return f"{n['DEF']}-{n['MID']}-{n['FWD']}"


def template_xi(players: list[dict[str, Any]]) -> dict:
    xi, own = _fill(players, "selected_by_percent")
    xi = sorted(xi, key=lambda p: (_POS_ORDER[p["position"]], -p.get("selected_by_percent", 0)))
    return {
        "formation": _formation_str(xi),
        "template_ownership": round(own, 1),
        "xi": [
            {"player_id": p["player_id"], "web_name": p["web_name"], "position": p["position"],
             "selected_by_percent": p.get("selected_by_percent", 0.0)}
            for p in xi
        ],
    }


def template_diff(picks: list[dict[str, Any]], template: dict) -> dict:
    tmpl_ids = {p["player_id"] for p in template.get("xi", [])}
    pick_ids = {p["player_id"] for p in picks}
    return {
        "overlap": len(tmpl_ids & pick_ids),
        "your_differentials": sorted(pick_ids - tmpl_ids),
        "template_only": sorted(tmpl_ids - pick_ids),
    }


def gw_calendar(fixtures: list[dict[str, Any]], gameweeks: list[dict[str, Any]], *,
                from_gw: int, to_gw: int, team_ids: list[int]) -> list[dict]:
    out = []
    for g in sorted(gameweeks, key=lambda g: g["id"]):
        gid = g["id"]
        if not (from_gw <= gid <= to_gw):
            continue
        counts = dict.fromkeys(team_ids, 0)
        for f in fixtures:
            if f.get("gameweek_id") != gid:
                continue
            for t in (f["home_team_id"], f["away_team_id"]):
                if t in counts:
                    counts[t] += 1
        out.append({
            "gameweek_id": gid,
            "counts": counts,
            "blanks": sorted(t for t, n in counts.items() if n == 0),
            "doubles": sorted(t for t, n in counts.items() if n >= 2),
        })
    return out


def pick_overpowered_xi(players: list[dict[str, Any]]) -> dict:
    xi, total = _fill(players, "xp")
    xi = sorted(xi, key=lambda p: (_POS_ORDER[p["position"]], -p.get("xp", 0)))
    return {
        "formation": _formation_str(xi),
        "total_xp": round(total, 2),
        "total_cost": sum(p.get("now_cost", 0) for p in xi),
        "xi": [
            {"player_id": p["player_id"], "web_name": p["web_name"], "position": p["position"],
             "xp": round(p.get("xp", 0.0), 2), "now_cost": p.get("now_cost", 0)}
            for p in xi
        ],
    }
```
> **Note:** `pick_overpowered_xi` / `template_xi` ignore the £100m budget and the max-3-per-club
> rule in v1 (documented follow-up). `_fill` picks the best formation by summed metric.

- [ ] **Step 4:** `python -m pytest packages/tools -q` → **6 passed**. `python -m pytest -q -W error` → **164 passed** (158 + 6). `ruff` clean.
  `feat(tools): fplguru-tools — trends, template XI, DGW/BGW calendar, overpowered XI`

---

## Task 3: API endpoints

**Files:** `services/api/.../main.py`, `services/api/tests/test_tools_api.py` (new).

- [ ] **Step 1: failing test** — `services/api/tests/test_tools_api.py`:
```python
from datetime import UTC, datetime

from fplguru_core.models import (
    EntryPick, Fixture, Gameweek, LinkedTeam, Player, PlayerGwPrediction, Team,
)

_MV = "basic-v1"


async def _seed(db_session):
    db_session.add_all([Team(id=1, name="A", short_name="A"), Team(id=2, name="B", short_name="B")])
    db_session.add_all([
        Gameweek(id=5, name="GW5", deadline_time=datetime(2025, 9, 1, tzinfo=UTC), is_current=True),
        Gameweek(id=6, name="GW6", deadline_time=datetime(2025, 9, 8, tzinfo=UTC)),
    ])
    await db_session.commit()
    def mk(pid, pos, team, sel, tin=0, tout=0, dc=0, xp=0.0):
        return pid, Player(id=pid, team_id=team, first_name="x", second_name="y",
                           web_name=f"P{pid}", position=pos, now_cost=50, status="a",
                           selected_by_percent=sel, transfers_in_event=tin,
                           transfers_out_event=tout, cost_change_event=dc)
    roster = [
        mk(1, "GK", 1, 20), mk(2, "DEF", 1, 55, tin=900, dc=1), mk(3, "DEF", 2, 40),
        mk(4, "DEF", 1, 35), mk(5, "MID", 2, 50, tout=800, dc=-1), mk(6, "MID", 1, 45),
        mk(7, "MID", 2, 30), mk(8, "MID", 1, 25), mk(9, "FWD", 2, 60), mk(10, "FWD", 1, 33),
        mk(11, "FWD", 2, 22),
    ]
    db_session.add_all([p for _, p in roster])
    db_session.add(LinkedTeam(id=1, fpl_entry_id=7, manager_name="Sam"))
    await db_session.commit()
    db_session.add_all([
        PlayerGwPrediction(player_id=pid, gameweek_id=5, horizon_gw=1, model_version=_MV,
                           xp=float(pid))
        for pid, _ in roster
    ])
    db_session.add_all([
        Fixture(id=50, gameweek_id=5, home_team_id=1, away_team_id=2, home_difficulty=3,
                away_difficulty=3),
        Fixture(id=51, gameweek_id=5, home_team_id=2, away_team_id=1, home_difficulty=3,
                away_difficulty=3),
        Fixture(id=60, gameweek_id=6, home_team_id=1, away_team_id=2, home_difficulty=3,
                away_difficulty=3),   # team 1 & 2 both single in GW6
    ])
    db_session.add_all([
        EntryPick(linked_team_id=1, gameweek_id=5, player_id=2, slot=1, multiplier=1),
        EntryPick(linked_team_id=1, gameweek_id=5, player_id=9, slot=2, multiplier=1),
    ])
    await db_session.commit()


async def test_trends(client, db_session):
    await _seed(db_session)
    body = (await client.get("/trends")).json()
    assert body["transfers_in"][0]["player_id"] == 2
    assert body["transfers_out"][0]["player_id"] == 5
    assert body["price_risers"][0]["player_id"] == 2
    assert body["price_fallers"][0]["player_id"] == 5


async def test_template(client, db_session):
    await _seed(db_session)
    body = (await client.get("/template")).json()
    assert len(body["xi"]) == 11
    assert body["formation"].count("-") == 2


async def test_template_diff(client, db_session):
    await _seed(db_session)
    body = (await client.get("/entries/7/template-diff")).json()
    assert "overlap" in body and isinstance(body["your_differentials"], list)


async def test_calendar_flags_double_in_gw5(client, db_session):
    await _seed(db_session)
    body = (await client.get("/calendar?from_gw=5&to_gw=6")).json()
    gw5 = next(c for c in body if c["gameweek_id"] == 5)
    assert sorted(gw5["doubles"]) == [1, 2]
    gw6 = next(c for c in body if c["gameweek_id"] == 6)
    assert gw6["doubles"] == []


async def test_overpowered(client, db_session):
    await _seed(db_session)
    body = (await client.get("/overpowered?horizon=1")).json()
    assert len(body["xi"]) == 11
    assert 9 in {p["player_id"] for p in body["xi"]}   # highest-xp forward
```

- [ ] **Step 2: implement in `main.py`** — add `LinkedTeamLeague`? no. Add `from fplguru_tools import (gw_calendar, pick_overpowered_xi, template_diff, template_xi, trends)`. Add `"fplguru-tools"` to `services/api/pyproject.toml` deps; `pip install -r requirements-dev.txt`. Then:
```python
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
        .where(PlayerGwPrediction.model_version == _MODEL_VERSION,
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
```

- [ ] **Step 3:** `python -m pytest services/api/tests/test_tools_api.py -q` → **5 passed**. `python -m pytest -q -W error` → **169 passed** (164 + 5). `ruff` clean.
  `feat(api): free-tools endpoints — trends, template, calendar, overpowered`

---

## Task 4: web API client

**Files:** `apps/web/src/lib/api.ts`, `apps/web/src/lib/api.tools.test.ts` (new).

- [ ] **Step 1: failing test** — `apps/web/src/lib/api.tools.test.ts`:
```ts
import { describe, expect, it, vi } from "vitest";

import { getCalendar, getOverpowered, getTemplate, getTrends } from "./api";

const ok = (j: unknown) => ({ ok: true, json: async () => j });

describe("tools api", () => {
  it("getTrends", async () => {
    const f = vi.fn().mockResolvedValue(ok({ transfers_in: [] }));
    global.fetch = f as unknown as typeof fetch;
    await getTrends("http://api.test");
    expect(String(f.mock.calls[0][0])).toContain("/trends");
  });
  it("getCalendar passes range", async () => {
    const f = vi.fn().mockResolvedValue(ok([]));
    global.fetch = f as unknown as typeof fetch;
    await getCalendar("http://api.test", 5, 10);
    expect(String(f.mock.calls[0][0])).toContain("from_gw=5");
    expect(String(f.mock.calls[0][0])).toContain("to_gw=10");
  });
  it("getOverpowered + getTemplate", async () => {
    const f = vi.fn().mockResolvedValue(ok({ xi: [] }));
    global.fetch = f as unknown as typeof fetch;
    await getOverpowered("http://api.test", 5);
    await getTemplate("http://api.test");
    expect(String(f.mock.calls[0][0])).toContain("/overpowered?horizon=5");
    expect(String(f.mock.calls[1][0])).toContain("/template");
  });
});
```

- [ ] **Step 2: implement** — append to `apps/web/src/lib/api.ts`:
```ts
export type TrendRow = { player_id: number; web_name: string; position: string; value: number };
export type Trends = {
  transfers_in: TrendRow[];
  transfers_out: TrendRow[];
  price_risers: TrendRow[];
  price_fallers: TrendRow[];
  most_owned: TrendRow[];
};
export type TemplatePlayer = {
  player_id: number;
  web_name: string;
  position: string;
  selected_by_percent: number;
};
export type TemplateXI = {
  formation: string;
  template_ownership: number;
  xi: TemplatePlayer[];
};
export type CalendarWeek = {
  gameweek_id: number;
  counts: Record<string, number>;
  blanks: number[];
  doubles: number[];
};
export type OverpoweredPlayer = {
  player_id: number;
  web_name: string;
  position: string;
  xp: number;
  now_cost: number;
};
export type OverpoweredXI = {
  formation: string;
  total_xp: number;
  total_cost: number;
  xi: OverpoweredPlayer[];
};

export function getTrends(base: string, limit = 10) {
  return fetch(`${base}/trends?limit=${limit}`, { cache: "no-store" }).then(asJson<Trends>);
}
export function getTemplate(base: string) {
  return fetch(`${base}/template`, { cache: "no-store" }).then(asJson<TemplateXI>);
}
export function getCalendar(base: string, fromGw: number, toGw: number) {
  return fetch(`${base}/calendar?from_gw=${fromGw}&to_gw=${toGw}`, { cache: "no-store" }).then(
    asJson<CalendarWeek[]>,
  );
}
export function getOverpowered(base: string, horizon = 5) {
  return fetch(`${base}/overpowered?horizon=${horizon}`, { cache: "no-store" }).then(
    asJson<OverpoweredXI>,
  );
}
```

- [ ] **Step 3:** `./node_modules/.bin/vitest run` → **17 passed** (14 + 3).
  `feat(web): free-tools API clients`

---

## Task 5: web `/tools` hub

**Files:** create `apps/web/src/app/tools/page.tsx`, `apps/web/src/app/tools/ToolsHub.tsx`; modify `apps/web/src/app/layout.tsx`.

- [ ] **Step 1: `tools/page.tsx`** (server shell) → `<main className="p-8"><h1 className="text-2xl font-semibold">Tools</h1><ToolsHub /></main>`.

- [ ] **Step 2: `tools/ToolsHub.tsx`** (client) — a tab strip (`Trends` / `Template` / `Calendar` / `Overpowered XI`) with `useState` for the active tab; each tab lazily fetches its endpoint on first view and renders a simple table/list:
  - **Trends**: five short lists (in / out / risers / fallers / most-owned), each `web_name — value`.
  - **Template**: formation label + the XI grouped by position with ownership %.
  - **Calendar**: a GW-range control (two number inputs, default current→+6 — just default 1→8 if unknown) and a grid: rows = GWs, showing `DGW: TEAMS` / `BGW: TEAMS` (team ids are fine for v1; a follow-up maps to short names).
  - **Overpowered XI**: horizon `<select>` 1–10, formation + total xP + the XI.
  Keep styling consistent with `/fdr` / `/alerts` (Tailwind, `border-collapse` tables). No persistence needed.

- [ ] **Step 3: `layout.tsx`** — add `<a href="/tools">Tools</a>` to the `<nav>` after `/leagues`.

- [ ] **Step 4:** `./node_modules/.bin/vitest run` → **17 passed** (unchanged). `./node_modules/.bin/next build` → success; `/tools` in the route list.
  `feat(web): /tools hub — trends, template, calendar, overpowered XI`

---

## Task 6: docs

**Files:** `README.md`, `docs/plans/2026-08-27-fplguru-master-build-plan.md`, `docs/RESUME-foundation.md`, `.env.example`.

- [ ] **Step 1: `.env.example`** — add a blank PitchAPI placeholder for the (now-decided) xG source, so P2a has a home:
```
# xG/xA data (P2a — PitchAPI, pitchapi.dev). Blank = xG features disabled.
FPLGURU_PITCHAPI_BASE=https://api.pitchapi.dev/v1
FPLGURU_PITCHAPI_KEY=
```
- [ ] **Step 2: `README.md`** — new "Tools" section listing the four endpoints (`GET /trends`, `/template`, `/entries/{id}/template-diff`, `/calendar?from_gw=&to_gw=`, `/overpowered?horizon=`) and noting the xG/CS snapshot lands with P2a. Note `players` now carries transfer/price/form fields (bootstrap sync fills them).
- [ ] **Step 3: master plan** — mark **P2i** ✅ (branch `feature/p2i-free-tools`); note "xG/CS Snapshot deferred to P2a"; record that **P2a's data source is decided: PitchAPI** (see `docs/` / memory). Decrement remaining count.
- [ ] **Step 4: `docs/RESUME-foundation.md`** — top status line + a `## P2i` section (task table + commits) + a line under the blocked list: "**xG source resolved 2026-08-27 → PitchAPI** (`pitchapi.dev`, `X-API-KEY`, opaque `p_` player ids need fuzzy FPL mapping). P2a is now unblocked."
- [ ] **Step 5: full verification** — `pytest -q -W error` → **169 passed**; `ruff` clean; `alembic check` clean; web `vitest run` → 17 passed; `next build` → success.
- [ ] **Step 6:** `docs: P2i Free Tools Suite complete`

---

## Self-Review

**Spec coverage (master §3 P2i / PRD §4.10):**
- GW Trends → `trends()` + `GET /trends` (transfers in/out, price risers/fallers, most-owned) ✓
- Template Analyser → `template_xi()` + `GET /template` + per-entry `GET /entries/{id}/template-diff` ✓
- DGW/BGW Calendar → `gw_calendar()` + `GET /calendar` ✓
- Overpowered 11 → `pick_overpowered_xi()` (max summed xP over a valid formation) + `GET /overpowered` ✓
- FDR/xG/CS Snapshot → **deferred to P2a** (PitchAPI ingestion + FPL id mapping); FDR already shipped in P1d with att/def split covering scoring-vs-cleansheet difficulty ✓ (explicit defer)

**Type/name consistency:**
- `trends(players, *, limit)`, `template_xi(players)`, `template_diff(picks, template)`,
  `gw_calendar(fixtures, gameweeks, *, from_gw, to_gw, team_ids)`, `pick_overpowered_xi(players)`
  — Task 2 defs == Task 3 calls ✓
- `_player_dicts` keys feed `trends`/`template_xi`/`pick_overpowered_xi`; `pick_overpowered_xi`
  additionally needs `xp` (merged in the `/overpowered` route) ✓
- API JSON shapes == web `Trends` / `TemplateXI` / `CalendarWeek` / `OverpoweredXI` ✓
- `players` new columns == `normalize_players` keys == migration `add_column`s == `_player_dicts` ✓

**Migration drift:** `0009` adds four non-null columns with `server_default='0'` matching the model;
`alembic check` in Task 1; no new table so `test_expected_tables_registered` untouched.

**Placeholder scan:** Task 5 describes the four tab views rather than giving full TSX — acceptable
for spec-check (shapes fully defined in Task 2/4; the components are presentational). Everything
Python/pure has complete code.

---

## Execution Handoff

Branch `feature/p2i-free-tools` off `main`. Subagent-driven, order 1 → 6. Task 2 (the four pure
computations) + Task 3 (API wiring) get a full review; Tasks 1, 4 spec-check + quality-check;
Tasks 5, 6 spec-check. After Task 6: whole-branch review, PR → `main`, watch CI, squash-merge.

### Deferred follow-ups
- Budget (£100m) + max-3-per-club constraints in `pick_overpowered_xi` / `template_xi`.
- Calendar: map team ids → short names in the API response.
- FDR/xG/CS Snapshot tool — with P2a (PitchAPI).
- "Template" as a 15-man squad (not just XI); ownership-weighted differentials scoring.
- Trends over a rolling window (needs a `player_gw` snapshot of transfers, not just the live `_event` field).
