# P1d — FDR Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** A platform-computed Fixture Difficulty Rating grid — for every team, the next N gameweeks' opponents scored 1.0–5.0 (attack difficulty, defence difficulty, and a combined number), blending FPL's coarse strength tier with each opponent's real goals-for / goals-against form. Served on `GET /fdr` and shown as a colour-coded, sortable grid on `/fdr` with a persisted 1–10 horizon selector.

**Architecture:** A pure `packages/fdr` package (`compute_fdr(teams, fixtures, gameweeks, *, start_gw, horizon, form_window=5) -> list[TeamFdr]`, no DB / no network). API `GET /fdr?horizon=&start_gw=` loads `Team` + `Fixture` + `Gameweek` and calls it. Web: typed client + a grid page (teams as rows, GWs as columns) + `localStorage` horizon.

**Scope note:** no tiers (see master-plan scope override) — the horizon selector exposes **1–10** to everyone. Understat xG/CS columns are a later add (sub-plan P2a is blocked on the xG-data decision); P1d's difficulty uses **FPL strength tier + FPL result form** only.

**Tech Stack / conventions:** unchanged — Python 3.12, FastAPI, SQLAlchemy async, Next 16 + Vitest, `venv`+`pip`, `python -m <tool>`, commits `git add -A -- ':!docs'`, author `Anil Kujur <anilkuj@gmail.com>` + `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`. Branch: `feature/p1d-fdr` off `main`.

**Reference:** master plan §3 P1d, PRD §4.6.

---

## Context (built: Foundation + P1c + P1a)

- `fplguru_core.models.Team` (`id`, `short_name`, `name`, `strength_overall_home`, `strength_overall_away` — small int **3–5** preseason; `strength_attack_*` / `strength_defence_*` are **0** until the season is underway). `Fixture` (`id`, `gameweek_id` nullable, `home_team_id`, `away_team_id`, `home_difficulty`, `away_difficulty`, `finished`, `home_score` / `away_score` nullable, `kickoff_time`). `Gameweek` (`id`, `is_next`, `finished`, `deadline_time`).
- `fplguru_core.db.get_sessionmaker()`. `services/api/main.py` — `get_db` (read-only), `_MODEL_VERSION`, endpoints incl. `/gameweeks/current`. Imports `from sqlalchemy import desc, distinct, func, select, text`.
- Root `conftest.py`: `db_engine`, `db_session` (opt-in, truncate-after), autouse `_point_app_at_test_db`. **FK-parent-first seeding** (no `relationship()`).
- `apps/web`: Next 16 App Router, Tailwind v4, Vitest 4. `src/lib/api.ts` has `fetchStatus`, `linkEntry`, `getEntry`, `getEntryHistory`. Nav in `src/app/layout.tsx` has greyed `<span>FDR</span>` placeholders. `NEXT_PUBLIC_API_BASE`.
- `ruff` local + CI (`E,F,I,UP,B`, line 100), `alembic/*` exempt for E402/E501/I001/UP035/UP007. **No new migration in P1d** (no new tables).

---

## FDR model

For team **T** playing opponent **O** at venue `v ∈ {home, away}` in a target gameweek:

1. **Strength component** (always available). Normalise O's venue-appropriate overall strength to 0–1:
   `s = (O.strength_overall_home if T is away else O.strength_overall_away)`  (opponent's rating *at the venue they play*, i.e. if T is home, O plays away → `O.strength_overall_away`).
   `strength_fdr = 1.0 + 4.0 * clamp((s - 2) / 3, 0, 1)`  → s=3→2.33, 4→3.67, 5→5.0 (min plausible s≈2).
2. **Form component** (only if O has ≥1 finished fixture with a score). From O's last `form_window` finished fixtures compute per-game `gf` (goals for) and `ga` (goals against). League baseline `B` = mean `gf` across all teams that have finished fixtures (≈1.4; fall back to 1.4 if none).
   - `att_form_fdr` (how hard for T to score → O's defensive form): `1.0 + 4.0 * clamp(1 - (O.ga / (2*B)), 0, 1)` — O conceding 0/game → 5.0; conceding 2·B → 1.0.
   - `def_form_fdr` (how hard for T's defence → O's attacking form): `1.0 + 4.0 * clamp(O.gf / (2*B), 0, 1)`.
3. **Blend** (weight `w_form = 0.45` when form available, else 0):
   - `att_fdr = (1 - w) * strength_fdr + w * att_form_fdr`
   - `def_fdr = (1 - w) * strength_fdr + w * def_form_fdr`
   - `fdr = (att_fdr + def_fdr) / 2`
   All three rounded to 2 dp. A 1–5 integer `band = round(fdr)` for colouring.

Per team over the horizon: `avg_fdr` = mean `fdr` across their fixtures in the window (used to sort "best fixtures first"). BGW → a team simply has fewer/no fixture entries for that GW; DGW → 2 entries for that GW.

---

## Task 1: `packages/fdr` — pure computation

**Files:** create `packages/fdr/pyproject.toml`, `src/fplguru_fdr/__init__.py`; add `-e ./packages/fdr` to `requirements-dev.txt`; create `packages/fdr/tests/test_fdr.py`.

- [ ] **Step 1: package skeleton**

`packages/fdr/pyproject.toml`:
```toml
[project]
name = "fplguru-fdr"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/fplguru_fdr"]
```
Add `-e ./packages/fdr` to `requirements-dev.txt` after `-e ./packages/entrysync`. `python -m pip install -r requirements-dev.txt`.

- [ ] **Step 2: failing test** — `packages/fdr/tests/test_fdr.py`:
```python
from fplguru_fdr import compute_fdr


def _team(tid, sn, sh, sa):
    return {"id": tid, "short_name": sn, "strength_overall_home": sh, "strength_overall_away": sa}


def _fx(fid, gw, h, a, hs=None, as_=None, finished=False):
    return {"id": fid, "gameweek_id": gw, "home_team_id": h, "away_team_id": a,
            "home_score": hs, "away_score": as_, "finished": finished}


TEAMS = [_team(1, "AAA", 5, 5), _team(2, "BBB", 3, 3), _team(3, "CCC", 4, 4)]
GWS = [{"id": g, "is_next": g == 4, "finished": g < 4} for g in range(1, 9)]


def test_preseason_is_strength_only():
    # no finished fixtures with scores -> form weight 0
    fx = [_fx(40, 4, 2, 1), _fx(41, 5, 1, 2)]
    out = {t["short_name"]: t for t in compute_fdr(TEAMS, fx, GWS, start_gw=4, horizon=2)}
    bbb = out["BBB"]
    # GW4: BBB home vs AAA(away strength 5) -> strength_fdr = 5.0 for both att and def
    f0 = next(f for f in bbb["fixtures"] if f["gameweek_id"] == 4)
    assert f0["is_home"] is True and f0["opponent_short"] == "AAA"
    assert abs(f0["fdr"] - 5.0) < 1e-6 and f0["band"] == 5
    # AAA at home vs weak BBB(away 3) -> strength_fdr = 1 + 4*((3-2)/3) = 2.333
    aaa = out["AAA"]
    f1 = next(f for f in aaa["fixtures"] if f["gameweek_id"] == 5)
    assert abs(f1["fdr"] - (1.0 + 4.0 * (1 / 3))) < 1e-6


def test_form_pulls_fdr_toward_recent_results():
    # CCC has leaked goals recently -> lower att_fdr (easier to score against) for opponents
    finished = [
        _fx(1, 1, 3, 1, hs=0, as_=4, finished=True),   # CCC 0-4
        _fx(2, 2, 2, 3, hs=3, as_=0, finished=True),   # CCC 0-3 (away)
        _fx(3, 3, 3, 1, hs=1, as_=3, finished=True),   # CCC 1-3
    ]
    fut = [_fx(40, 4, 2, 3)]   # BBB home vs CCC away
    out = {t["short_name"]: t for t in compute_fdr(TEAMS, finished + fut, GWS, start_gw=4, horizon=1)}
    f = out["BBB"]["fixtures"][0]
    # CCC ga_pg ~3.33 >> baseline -> att_form_fdr near 1 -> blended att_fdr below strength_fdr(4)
    assert f["att_fdr"] < f["def_fdr"]  # scoring against CCC is "easy", CS is not
    assert 1.0 <= f["fdr"] <= 5.0


def test_avg_fdr_present_and_sorted_input_ok():
    fx = [_fx(40, 4, 1, 2), _fx(41, 5, 2, 1), _fx(42, 4, 3, 1)]
    out = compute_fdr(TEAMS, fx, GWS, start_gw=4, horizon=3)
    for t in out:
        assert "avg_fdr" in t and (t["avg_fdr"] is None or 1.0 <= t["avg_fdr"] <= 5.0)
    assert {t["short_name"] for t in out} == {"AAA", "BBB", "CCC"}
```

- [ ] **Step 3: implement `packages/fdr/src/fplguru_fdr/__init__.py`**:
```python
"""Platform FDR: opponent strength tier blended with recent goals-for/against form.

Pure — takes plain dicts, returns plain dicts. No DB, no network.
"""
from __future__ import annotations

_FORM_W = 0.45
_DEFAULT_BASELINE = 1.4

__all__ = ["compute_fdr"]


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _strength_fdr(s: int | None) -> float:
    if s is None:
        return 3.0
    return 1.0 + 4.0 * _clamp((s - 2) / 3.0, 0.0, 1.0)


def compute_fdr(teams, fixtures, gameweeks, *, start_gw: int, horizon: int,
                form_window: int = 5) -> list[dict]:
    by_id = {t["id"]: t for t in teams}
    short = {t["id"]: t["short_name"] for t in teams}
    target_gws = {
        g["id"] for g in gameweeks if start_gw <= g["id"] < start_gw + horizon
    }

    # --- recent form from finished fixtures with scores ---
    played: dict[int, list[tuple[int, int]]] = {}  # team_id -> [(gf, ga), ...] oldest-first
    ordered = sorted(
        (f for f in fixtures if f["finished"] and f["home_score"] is not None
         and f["away_score"] is not None),
        key=lambda f: (f["gameweek_id"] or 0, f["id"]),
    )
    for f in ordered:
        h, a = f["home_team_id"], f["away_team_id"]
        hs, as_ = f["home_score"], f["away_score"]
        played.setdefault(h, []).append((hs, as_))
        played.setdefault(a, []).append((as_, hs))

    def form(team_id: int) -> tuple[float, float] | None:
        rows = played.get(team_id, [])[-form_window:]
        if not rows:
            return None
        gf = sum(r[0] for r in rows) / len(rows)
        ga = sum(r[1] for r in rows) / len(rows)
        return gf, ga

    all_gf = [gf for tid in played for gf, _ in [form(tid)] if gf is not None]
    baseline = (sum(all_gf) / len(all_gf)) if all_gf else _DEFAULT_BASELINE

    out: list[dict] = []
    for t in teams:
        tid = t["id"]
        rows = []
        for f in fixtures:
            if f["gameweek_id"] not in target_gws:
                continue
            if tid == f["home_team_id"]:
                is_home, opp = True, f["away_team_id"]
            elif tid == f["away_team_id"]:
                is_home, opp = False, f["home_team_id"]
            else:
                continue
            opp_t = by_id.get(opp, {})
            opp_venue_strength = (
                opp_t.get("strength_overall_away") if is_home
                else opp_t.get("strength_overall_home")
            )
            s_fdr = _strength_fdr(opp_venue_strength)

            opp_form = form(opp)
            if opp_form is None:
                att_fdr = def_fdr = s_fdr
                opp_form_out = None
            else:
                gf, ga = opp_form
                att_form = 1.0 + 4.0 * _clamp(1.0 - ga / (2.0 * baseline), 0.0, 1.0)
                def_form = 1.0 + 4.0 * _clamp(gf / (2.0 * baseline), 0.0, 1.0)
                att_fdr = (1 - _FORM_W) * s_fdr + _FORM_W * att_form
                def_fdr = (1 - _FORM_W) * s_fdr + _FORM_W * def_form
                opp_form_out = {"gf_pg": round(gf, 2), "ga_pg": round(ga, 2)}

            fdr = (att_fdr + def_fdr) / 2.0
            rows.append({
                "gameweek_id": f["gameweek_id"],
                "opponent_id": opp,
                "opponent_short": short.get(opp, "?"),
                "is_home": is_home,
                "att_fdr": round(att_fdr, 2),
                "def_fdr": round(def_fdr, 2),
                "fdr": round(fdr, 2),
                "band": int(round(fdr)),
                "opponent_form": opp_form_out,
            })
        rows.sort(key=lambda r: (r["gameweek_id"], r["opponent_id"]))
        avg = round(sum(r["fdr"] for r in rows) / len(rows), 2) if rows else None
        out.append({
            "team_id": tid, "short_name": t["short_name"],
            "avg_fdr": avg, "fixtures": rows,
        })
    out.sort(key=lambda t: (t["avg_fdr"] is None, t["avg_fdr"] or 0.0))
    return out
```

- [ ] **Step 4:** run → 3 passed. `python -m pytest -q` (repo root) → +3. `python -m ruff check .` → clean. Commit `feat(fdr): platform FDR computation (strength tier + result form)`.

---

## Task 2: API `GET /fdr`

**Files:** modify `services/api/src/fplguru_api/main.py`, `services/api/pyproject.toml`; create `services/api/tests/test_fdr_api.py`.

- [ ] **Step 1: deps** — add `"fplguru-fdr"` to `services/api/pyproject.toml`. `pip install -r requirements-dev.txt`.

- [ ] **Step 2: failing test** — `services/api/tests/test_fdr_api.py`:
```python
from datetime import UTC, datetime

from fplguru_core.models import Fixture, Gameweek, Team


async def _seed(db_session):
    db_session.add_all([
        Team(id=1, name="Aaa", short_name="AAA", strength_overall_home=5, strength_overall_away=5),
        Team(id=2, name="Bbb", short_name="BBB", strength_overall_home=3, strength_overall_away=3),
        Team(id=3, name="Ccc", short_name="CCC", strength_overall_home=4, strength_overall_away=4),
    ])
    db_session.add_all([
        Gameweek(id=g, name=f"GW{g}", deadline_time=datetime(2025, 8, g, tzinfo=UTC),
                 finished=g < 4, is_next=g == 4)
        for g in range(1, 9)
    ])
    await db_session.commit()
    db_session.add_all([
        Fixture(id=1, gameweek_id=1, home_team_id=3, away_team_id=1, home_difficulty=3,
                away_difficulty=3, finished=True, home_score=0, away_score=4),
        Fixture(id=40, gameweek_id=4, home_team_id=2, away_team_id=3, home_difficulty=3,
                away_difficulty=3, finished=False),
        Fixture(id=41, gameweek_id=5, home_team_id=1, away_team_id=2, home_difficulty=3,
                away_difficulty=3, finished=False),
    ])
    await db_session.commit()


async def test_fdr_defaults_to_next_gw(client, db_session):
    await _seed(db_session)
    r = await client.get("/fdr?horizon=5")
    body = r.json()
    assert body["start_gw"] == 4 and body["horizon"] == 5
    teams = {t["short_name"]: t for t in body["teams"]}
    bbb = teams["BBB"]
    f = next(x for x in bbb["fixtures"] if x["gameweek_id"] == 4)
    assert f["opponent_short"] == "CCC" and f["is_home"] is True
    assert 1.0 <= f["fdr"] <= 5.0 and 1 <= f["band"] <= 5
    # teams are returned easiest-fixtures-first (lowest avg_fdr)
    avgs = [t["avg_fdr"] for t in body["teams"] if t["avg_fdr"] is not None]
    assert avgs == sorted(avgs)


async def test_fdr_explicit_start_and_horizon_clamp(client, db_session):
    await _seed(db_session)
    r = await client.get("/fdr?start_gw=5&horizon=1")
    body = r.json()
    assert body["start_gw"] == 5
    aaa = next(t for t in body["teams"] if t["short_name"] == "AAA")
    assert [f["gameweek_id"] for f in aaa["fixtures"]] == [5]


async def test_fdr_horizon_out_of_range_422(client, db_session):
    await _seed(db_session)
    assert (await client.get("/fdr?horizon=0")).status_code == 422
    assert (await client.get("/fdr?horizon=11")).status_code == 422
```

- [ ] **Step 3: implement in `main.py`** — `from fplguru_fdr import compute_fdr`; add `Fixture, Team` to the models import if missing. Then:
```python
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
```

- [ ] **Step 4:** run api tests → green. `pytest -q` + `ruff` + `alembic check` clean. Commit `feat(api): GET /fdr (platform fixture-difficulty grid)`.

---

## Task 3: web — FDR page

**Files:** modify `apps/web/src/lib/api.ts`, `apps/web/src/app/layout.tsx`; create `apps/web/src/app/fdr/page.tsx`, `apps/web/src/app/fdr/FdrGrid.tsx`, `apps/web/src/lib/api.fdr.test.ts`; modify `apps/web/src/lib/entry.ts` (add a generic pref helper) OR create `apps/web/src/lib/prefs.ts`.

- [ ] **Step 1: failing test** — `apps/web/src/lib/api.fdr.test.ts`:
```ts
import { describe, expect, it, vi } from "vitest";
import { getFdr } from "./api";

describe("getFdr", () => {
  it("passes horizon and returns the grid", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ start_gw: 4, horizon: 5, teams: [] }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;
    const r = await getFdr("http://api.test", 5);
    expect(r.start_gw).toBe(4);
    expect(String(fetchMock.mock.calls[0][0])).toContain("horizon=5");
  });
});
```

- [ ] **Step 2: `api.ts`** (append):
```ts
export type FdrFixture = {
  gameweek_id: number;
  opponent_short: string;
  is_home: boolean;
  fdr: number;
  att_fdr: number;
  def_fdr: number;
  band: number;
  opponent_form: { gf_pg: number; ga_pg: number } | null;
};
export type FdrTeam = { team_id: number; short_name: string; avg_fdr: number | null; fixtures: FdrFixture[] };
export type FdrGridData = { start_gw: number; horizon: number; teams: FdrTeam[] };

export function getFdr(base: string, horizon: number, startGw?: number) {
  const q = new URLSearchParams({ horizon: String(horizon) });
  if (startGw) q.set("start_gw", String(startGw));
  return fetch(`${base}/fdr?${q}`, { cache: "no-store" }).then(asJson<FdrGridData>);
}
```
(`asJson` already exists from P1a.)

- [ ] **Step 3: `apps/web/src/lib/prefs.ts`** — small typed localStorage helper:
```ts
export function getPref(key: string, fallback: number): number {
  try {
    const v = typeof window !== "undefined" ? window.localStorage.getItem(`fplguru.${key}`) : null;
    const n = v ? Number(v) : NaN;
    return Number.isFinite(n) ? n : fallback;
  } catch {
    return fallback;
  }
}
export function setPref(key: string, value: number): void {
  try {
    window.localStorage.setItem(`fplguru.${key}`, String(value));
  } catch {
    /* ignore */
  }
}
```

- [ ] **Step 4: `apps/web/src/app/fdr/page.tsx`** + `FdrGrid.tsx` (client). The grid: teams as rows (already easiest-first from the API), one column per GW in `[start_gw, start_gw+horizon)`, each cell = opponent short + `(H/A)` coloured by `band` (1 green → 5 red via Tailwind classes: `bg-emerald-200 bg-lime-200 bg-amber-200 bg-orange-200 bg-red-300`). A `<select>` for horizon 1–10 wired to `getPref("fdrHorizon", 5)` / `setPref`. `page.tsx` renders `<FdrGrid/>`; `FdrGrid` does the `useEffect` fetch. Header row shows `GW{n}`.

```tsx
// fdr/page.tsx
import { FdrGrid } from "./FdrGrid";
export default function FdrPage() {
  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">Fixture difficulty</h1>
      <FdrGrid />
    </main>
  );
}
```
```tsx
// fdr/FdrGrid.tsx
"use client";
import { useEffect, useMemo, useState } from "react";
import { type FdrGridData, getFdr } from "@/lib/api";
import { getPref, setPref } from "@/lib/prefs";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const CLR = ["", "bg-emerald-200", "bg-lime-200", "bg-amber-200", "bg-orange-200", "bg-red-300"];

export function FdrGrid() {
  const [horizon, setHorizon] = useState(5);
  const [data, setData] = useState<FdrGridData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { setHorizon(getPref("fdrHorizon", 5)); }, []);
  useEffect(() => {
    setErr(null);
    getFdr(API, horizon).then(setData).catch(() => setErr("Could not load FDR."));
  }, [horizon]);

  const cols = useMemo(
    () => (data ? Array.from({ length: data.horizon }, (_, i) => data.start_gw + i) : []),
    [data],
  );

  return (
    <>
      <label className="mt-2 block text-sm text-gray-500">
        Horizon{" "}
        <select
          value={horizon}
          onChange={(e) => { const h = Number(e.target.value); setHorizon(h); setPref("fdrHorizon", h); }}
          className="border rounded px-2 py-1"
        >
          {Array.from({ length: 10 }, (_, i) => i + 1).map((h) => (
            <option key={h} value={h}>{h}</option>
          ))}
        </select>
      </label>
      {err && <p className="mt-3 text-sm text-red-600">{err}</p>}
      {data && (
        <div className="mt-4 overflow-x-auto">
          <table className="text-sm border-collapse">
            <thead>
              <tr>
                <th className="text-left px-2 py-1">Team</th>
                <th className="px-2 py-1">Avg</th>
                {cols.map((g) => <th key={g} className="px-2 py-1">GW{g}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.teams.map((t) => (
                <tr key={t.team_id} className="border-t">
                  <td className="px-2 py-1 font-medium">{t.short_name}</td>
                  <td className="px-2 py-1 text-center text-gray-500">{t.avg_fdr ?? "—"}</td>
                  {cols.map((g) => {
                    const fs = t.fixtures.filter((f) => f.gameweek_id === g);
                    return (
                      <td key={g} className="px-1 py-1 text-center">
                        {fs.length === 0 ? <span className="text-gray-300">—</span> : fs.map((f, i) => (
                          <span key={i} className={`inline-block rounded px-1 mx-0.5 ${CLR[f.band] ?? ""}`}>
                            {f.opponent_short}{f.is_home ? " (H)" : " (A)"}
                          </span>
                        ))}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 5: `layout.tsx`** — change the greyed `<span className="text-gray-400">FDR</span>` to `<a href="/fdr">FDR</a>`.

- [ ] **Step 6:** `pnpm --filter web test` → +1 (getFdr). `pnpm --filter web build` → clean (`/fdr` prerenders — the fetch is client-side). Commit `feat(web): FDR grid page with horizon selector`.

---

## Task 4: docs

- [ ] `README.md` — under the API list add `GET /fdr?horizon=5`.
- [ ] `docs/plans/2026-08-27-fplguru-master-build-plan.md` — mark **P1d** ✅; note "FDR from FPL strength tier + result form; xG/CS columns pending P2a".
- [ ] `docs/RESUME-foundation.md` — add a P1d row.
- [ ] Full `python -m pytest -q -W error`, `python -m ruff check .`, `python -m alembic check`, `pnpm --filter web test`, `pnpm --filter web build` → all clean.
- [ ] Commit `chore: P1d docs`, then `docs: P1d complete`.

---

## Self-Review

**Spec coverage (master §3 P1d / PRD §4.6):**
- Platform-computed FDR per team, not raw FPL fixture difficulty → Task 1 ✓ (strength tier + result form blend)
- Horizon selector 1–10, all users (no tier) → Tasks 2, 3 ✓
- Colour-coded grid, sortable → Task 3 (easiest-first from API `avg_fdr` sort) ✓
- xG-for/against + clean-sheet-probability columns → **deferred** — needs Understat (P2a, blocked). `att_fdr` / `def_fdr` split partially covers the intent (scoring vs clean-sheet difficulty).
- Preference persisted → `prefs.ts` localStorage ✓

**Type/name consistency:**
- `compute_fdr(teams, fixtures, gameweeks, *, start_gw, horizon, form_window=5) -> list[dict]` — Task 1 def == Task 2 call ✓
- Fixture dicts passed to `compute_fdr` use `home_score`/`away_score`/`finished`/`gameweek_id` — match `Fixture` columns ✓
- web `FdrTeam`/`FdrFixture`/`FdrGridData` mirror the API JSON ✓
- No new DB tables → no migration, `alembic check` stays clean ✓

**Placeholder scan:** none — all code complete.

---

## Execution Handoff

Branch `feature/p1d-fdr` off `main`. Subagent-driven. Order 1 → 2 → 3 → 4. Task 1 (the FDR math) gets full review; 2–4 spec-check.
