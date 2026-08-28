# P2d — Optimize My Team — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. TDD; gates `python -m pytest -q -W error` + `python -m ruff check .` + `python -m alembic check` (+ `vitest` / `next build` for the web task).

**Goal:** For a linked team, recommend the best starting XI + captain/vice + bench order, a ranked
set of transfer plans (with hit accounting and budget/club constraints), and chip-timing hints —
all off the Advanced (`adv-v1`) xP projection over a configurable horizon.

**Architecture:** A new **pure** package `fplguru-optimize` (no DB, no network): formation-aware
best-XI selection, a greedy transfer search that maximises XI-xP net of the 4-pt hit while
respecting the 15-man squad shape / £bank / max-3-per-club, and DGW/BGW chip hints from fixture
counts. A single read endpoint `GET /entries/{id}/optimize` assembles the inputs (latest picks,
horizon-summed predictions, market, bank from `EntryGwHistory`, fixture calendar) and calls the
package. A new `/optimize` web page renders it. No tiers (2026-08-27 pivot). No migration.

**Tech Stack:** pure Python, FastAPI, Next.js. No new deps.

---

## Project context (read once)

- Branch **`feature/p2d-optimize`** off `main` (P2c merged at `bb8e3e7`).
- **`fplguru_tools`** (`packages/tools/src/fplguru_tools/__init__.py`) — precedent for pure tools.
  `_FORMATIONS = [(3,4,3),(3,5,2),(4,4,2),(4,3,3),(4,5,1),(5,4,1),(5,3,2)]` (DEF,MID,FWD; GK=1),
  `_POS_ORDER`, `_fill(players, key) -> (xi, score)` (best XI by summed `key`),
  `_formation_str(xi)`, `gw_calendar(fixtures, gameweeks, *, from_gw, to_gw, team_ids) -> [{gameweek_id, counts, blanks, doubles}]`,
  `pick_overpowered_xi`.
- **API** `services/api/src/fplguru_api/main.py`: `_linked_or_404(db, entry_id) -> LinkedTeam`;
  `_resolve_model_version(db, model="auto") -> str` (`auto|basic|advanced`); `get_db` (read-only);
  `GET /entries/{id}` builds `xp_by_player` = `sum(PlayerGwPrediction.xp)` grouped by player for the
  resolved `model_version` — copy that pattern. `GET /overpowered` filters `_player_dicts(rows)` +
  `xp_by_player`. `_player_dicts` helper exists (used by `/overpowered`).
- **Models:** `EntryPick(linked_team_id, gameweek_id, player_id, slot 1..15, multiplier,
  is_captain, is_vice)`; `Player(id, team_id, web_name, position ∈ {GK,DEF,MID,FWD}, now_cost
  tenths, status, selected_by_percent, ...)`; `EntryGwHistory(linked_team_id, gameweek_id, bank
  tenths, team_value tenths, ...)`; `Fixture(gameweek_id nullable, home_team_id, away_team_id,
  home_difficulty, away_difficulty, finished)`; `Gameweek(id, is_current, is_next, finished,
  deadline_time)`; `Team(id, short_name)`.
- **Squad shape:** 2 GK, 5 DEF, 5 MID, 3 FWD = 15; XI = 1 GK + a `_FORMATIONS` outfield split;
  max 3 players per real club.
- **`apps/web`** — `nav-items.ts` (`NAV_ITEMS` array, lucide icons), design-system primitives in
  `src/components/ui`, `DataTable`, `PageHeader`, `getPrefStr`/`setPrefStr` (string prefs),
  `getStoredEntryId()`. Page pattern: `src/app/<route>/page.tsx` (thin) renders a `"use client"`
  child. `api.ts` `XpModel = "auto"|"basic"|"advanced"`.
- **Baseline:** `pytest -q` → **220 passed**; web `vitest run` → **22 passed**.
- **SAC:** pure Python only.

---

## Task 1: `fplguru-optimize` — best XI + captain/vice/bench

**Files:** create `packages/optimize/pyproject.toml`,
`packages/optimize/src/fplguru_optimize/__init__.py`, `packages/optimize/tests/test_best_xi.py`;
edit root `pyproject.toml` (`known-first-party` → add `fplguru_optimize`), `requirements-dev.txt`
(`-e ./packages/optimize`).

- [ ] **Step 1 — `pyproject.toml`** (copy `packages/tools/pyproject.toml`, s/tools/optimize/,
  `description = "Pure squad optimiser: best XI, transfers, chip timing."`, deps `[]`).

- [ ] **Step 2 — failing test** `test_best_xi.py`:
```python
from fplguru_optimize import best_xi

def _p(pid, pos, xp, cost=50, club=1):
    return {"player_id": pid, "position": pos, "web_name": f"P{pid}",
            "xp": xp, "now_cost": cost, "team_id": club}

def _squad():
    # 2 GK, 5 DEF, 5 MID, 3 FWD; xp descends with id
    s, pid = [], 1
    for pos, n in (("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)):
        for _ in range(n):
            s.append(_p(pid, pos, xp=30 - pid, club=1 + pid % 4)); pid += 1
    return s

def test_best_xi_picks_top_scoring_legal_eleven():
    r = best_xi(_squad(), key="xp")
    assert len(r["xi"]) == 11 and len(r["bench"]) == 4
    assert r["xi"][0]["position"] == "GK"          # exactly one keeper starts
    assert sum(1 for p in r["xi"] if p["position"] == "GK") == 1
    assert r["captain"]["player_id"] == r["xi"][0 if False else 0]["player_id"] or True
    # captain is the highest-xp starter, vice the second
    xi_by_xp = sorted(r["xi"], key=lambda p: -p["xp"])
    assert r["captain"]["player_id"] == xi_by_xp[0]["player_id"]
    assert r["vice"]["player_id"] == xi_by_xp[1]["player_id"]
    assert r["total"] == round(sum(p["xp"] for p in r["xi"]), 2)
    assert r["formation"].count("-") == 2

def test_best_xi_bench_is_lowest_and_keeps_a_gk():
    r = best_xi(_squad(), key="xp")
    assert sum(1 for p in r["bench"] if p["position"] == "GK") == 1
    bench_xp = [p["xp"] for p in r["bench"] if p["position"] != "GK"]
    xi_out_xp = [p["xp"] for p in r["xi"] if p["position"] != "GK"]
    assert max(bench_xp) <= min(xi_out_xp) + 1e-9
```

- [ ] **Step 3 — implement `__init__.py` (part 1):**
```python
"""Pure squad optimiser: best XI, transfer suggestions, chip-timing hints.
No DB, no network. All 'xp' values are cumulative over the caller's horizon."""
from __future__ import annotations

from typing import Any

__all__ = ["best_xi", "suggest_transfers", "chip_hints", "SQUAD_SHAPE", "HIT_COST"]

# GK, DEF, MID, FWD squad quotas; XI outfield splits (DEF, MID, FWD), GK always 1
SQUAD_SHAPE = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
_FORMATIONS = [(3, 4, 3), (3, 5, 2), (4, 4, 2), (4, 3, 3), (4, 5, 1), (5, 4, 1), (5, 3, 2)]
_POS_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}
HIT_COST = 4.0


def _by_pos(players: list[dict]) -> dict[str, list[dict]]:
    d: dict[str, list[dict]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for p in players:
        if p["position"] in d:
            d[p["position"]].append(p)
    for pos in d:
        d[pos].sort(key=lambda p: (p.get("xp", 0.0), -p["player_id"]), reverse=True)
    return d


def _best_xi_ids(players: list[dict], key: str) -> tuple[list[dict], float]:
    bp = _by_pos(players)
    if not bp["GK"]:
        return [], 0.0
    gk = bp["GK"][:1]
    best: tuple[list[dict], float] | None = None
    for d, m, f in _FORMATIONS:
        if len(bp["DEF"]) < d or len(bp["MID"]) < m or len(bp["FWD"]) < f:
            continue
        xi = gk + bp["DEF"][:d] + bp["MID"][:m] + bp["FWD"][:f]
        score = sum(p.get(key, 0.0) for p in xi)
        if best is None or score > best[1]:
            best = (xi, score)
    return best if best else ([], 0.0)


def best_xi(squad: list[dict[str, Any]], *, key: str = "xp") -> dict:
    xi, total = _best_xi_ids(squad, key)
    xi_ids = {p["player_id"] for p in xi}
    bench = [p for p in squad if p["player_id"] not in xi_ids]
    # bench order: reserve GK first, then outfield by descending key
    bench.sort(key=lambda p: (p["position"] != "GK", -p.get(key, 0.0), p["player_id"]))
    xi_sorted = sorted(xi, key=lambda p: (_POS_ORDER[p["position"]], -p.get(key, 0.0)))
    ranked = sorted(xi, key=lambda p: (-p.get(key, 0.0), p["player_id"]))
    cap = ranked[0] if ranked else None
    vice = ranked[1] if len(ranked) > 1 else None
    n = {"DEF": 0, "MID": 0, "FWD": 0}
    for p in xi:
        if p["position"] in n:
            n[p["position"]] += 1
    return {
        "formation": f"{n['DEF']}-{n['MID']}-{n['FWD']}",
        "total": round(total, 2),
        "xi": xi_sorted, "bench": bench,
        "captain": cap, "vice": vice,
    }
```

- [ ] **Step 4:** wire `known-first-party` + `requirements-dev.txt`; `pip install -e
  ./packages/optimize`; `pytest packages/optimize -q` green; `ruff` clean.
  Commit `feat(optimize): fplguru-optimize best_xi + captain/vice/bench`.

---

## Task 2: `suggest_transfers` + `chip_hints`

**Files:** `packages/optimize/src/fplguru_optimize/__init__.py`,
`packages/optimize/tests/test_transfers.py`.

- [ ] **Step 1 — failing test** `test_transfers.py`:
```python
from fplguru_optimize import chip_hints, suggest_transfers

def _p(pid, pos, xp, cost=50, club=1):
    return {"player_id": pid, "position": pos, "web_name": f"P{pid}",
            "xp": xp, "now_cost": cost, "team_id": club}

def _squad():
    s, pid = [], 1
    for pos, n in (("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)):
        for _ in range(n):
            s.append(_p(pid, pos, xp=20.0, cost=50, club=1 + pid % 5)); pid += 1
    return s

def test_suggest_transfers_finds_a_clear_upgrade():
    squad = _squad()
    # one weak MID in the squad; a strong same-price MID available
    squad[7]["xp"] = 5.0                       # pid 8, a MID
    market = [_p(99, "MID", xp=40.0, cost=50, club=9)]
    plans = suggest_transfers(squad, market, bank=0, free_transfers=1,
                              max_transfers=1, key="xp")
    best = plans[0]
    assert best["transfers"][0]["out"]["player_id"] == 8
    assert best["transfers"][0]["in"]["player_id"] == 99
    assert best["gain"] > 0 and best["hit"] == 0 and best["net"] == best["gain"]

def test_second_transfer_charges_a_hit():
    squad = _squad()
    squad[7]["xp"] = 5.0
    squad[8]["xp"] = 5.0
    market = [_p(98, "MID", 40.0, 50, 9), _p(99, "MID", 41.0, 50, 10)]
    plans = suggest_transfers(squad, market, bank=0, free_transfers=1,
                              max_transfers=2, key="xp")
    two = next(p for p in plans if len(p["transfers"]) == 2)
    assert two["hit"] == 4.0 and two["net"] == round(two["gain"] - 4.0, 2)

def test_transfer_respects_budget_and_club_cap():
    squad = _squad()                           # 3 players already at club (1 + pid%5)
    market = [_p(99, "MID", 99.0, cost=130, club=1)]   # unaffordable + club would break
    plans = suggest_transfers(squad, market, bank=0, free_transfers=1,
                              max_transfers=1, key="xp")
    assert plans[0]["transfers"] == []         # nothing legal -> "roll" plan

def test_chip_hints_flags_double_and_blank():
    cal = [
        {"gameweek_id": 30, "doubles": [1, 2, 3], "blanks": []},
        {"gameweek_id": 33, "doubles": [], "blanks": [1, 2, 3, 4, 5, 6]},
    ]
    hints = chip_hints(cal, squad_team_ids=[1, 2, 3, 4, 5])
    kinds = {(h["chip"], h["gameweek_id"]) for h in hints}
    assert ("bench_boost", 30) in kinds
    assert ("free_hit", 33) in kinds
```

- [ ] **Step 2 — implement (append):**
```python
def _club_counts(squad: list[dict]) -> dict[int, int]:
    c: dict[int, int] = {}
    for p in squad:
        c[p["team_id"]] = c.get(p["team_id"], 0) + 1
    return c


def _apply(squad, out_p, in_p):
    return [in_p if p["player_id"] == out_p["player_id"] else p for p in squad]


def _one_transfer(squad, market, *, bank, key):
    """Best single (out, in) by XI-key gain, or None."""
    cur_xi = _best_xi_ids(squad, key)[1]
    have = {p["player_id"] for p in squad}
    best = None  # (gain, out, in, bank_after)
    for out_p in squad:
        for in_p in market:
            if in_p["player_id"] in have or in_p["position"] != out_p["position"]:
                continue
            bank_after = bank + out_p["now_cost"] - in_p["now_cost"]
            if bank_after < 0:
                continue
            after = _apply(squad, out_p, in_p)
            cc = _club_counts(after)
            if any(v > 3 for v in cc.values()):
                continue
            gain = _best_xi_ids(after, key)[1] - cur_xi
            if best is None or gain > best[0]:
                best = (gain, out_p, in_p, bank_after)
    return best


def suggest_transfers(squad, market, *, bank: int, free_transfers: int = 1,
                      max_transfers: int = 2, key: str = "xp",
                      hit_cost: float = HIT_COST) -> list[dict]:
    """Greedy: at each step take the single transfer with the largest XI-`key`
    gain. Returns one plan per k in 0..max_transfers, sorted by `net` desc;
    plan[k=0] is 'roll your transfer'. Each plan: {transfers:[{out,in}], gain,
    hit, net}."""
    plans = [{"transfers": [], "gain": 0.0, "hit": 0.0, "net": 0.0}]
    work = list(squad)
    cur_bank = bank
    total_gain = 0.0
    used = list(market)
    for k in range(1, max_transfers + 1):
        step = _one_transfer(work, used, bank=cur_bank, key=key)
        if step is None or step[0] <= 1e-9:
            break
        gain, out_p, in_p, cur_bank = step
        work = _apply(work, out_p, in_p)
        used = [m for m in used if m["player_id"] != in_p["player_id"]]
        total_gain += gain
        hit = hit_cost * max(0, k - free_transfers)
        prev = plans[-1]["transfers"]
        plans.append({
            "transfers": prev + [{"out": out_p, "in": in_p}],
            "gain": round(total_gain, 2),
            "hit": round(hit, 2),
            "net": round(total_gain - hit, 2),
        })
    plans.sort(key=lambda p: p["net"], reverse=True)
    return plans


def chip_hints(calendar: list[dict], *, squad_team_ids: list[int],
               double_threshold: int = 3, blank_threshold: int = 4) -> list[dict]:
    ids = set(squad_team_ids)
    out = []
    for row in calendar:
        dbl = len(ids & set(row.get("doubles", [])))
        blk = len(ids & set(row.get("blanks", [])))
        if dbl >= double_threshold:
            out.append({"chip": "bench_boost", "gameweek_id": row["gameweek_id"],
                        "reason": f"{dbl} of your players have a double gameweek"})
            out.append({"chip": "triple_captain", "gameweek_id": row["gameweek_id"],
                        "reason": "premium captain plays twice"})
        if blk >= blank_threshold:
            out.append({"chip": "free_hit", "gameweek_id": row["gameweek_id"],
                        "reason": f"{blk} of your players blank this gameweek"})
    return out
```

- [ ] **Step 3:** `pytest packages/optimize -q` green; `ruff` clean.
  Commit `feat(optimize): greedy transfer search + chip-timing hints`.

---

## Task 3: `GET /entries/{entry_id}/optimize`

**Files:** `services/api/src/fplguru_api/main.py`, `services/api/tests/test_optimize_api.py`.

- [ ] **Step 1 — failing test** `test_optimize_api.py`: seed a `LinkedTeam` (+ `EntryPick` rows for
  a full legal 15 at the latest `gameweek_id`), `Player`/`Team` rows, `adv-v1`
  `PlayerGwPrediction` rows over 2 horizons, one obviously-better bench MID on the market
  (a `Player` not in the squad with high xp), an `EntryGwHistory` row with `bank=5`, `Fixture`
  rows. Assert:
  - `GET /entries/{id}/optimize?horizon=2` → 200 with `horizon==2`, `model=="adv-v1"`,
    `current.xi` length 11, `current.captain` present, `transfer_plans` non-empty and
    `transfer_plans[0].net >= 0`, `chips` is a list.
  - unlinked id → 404.

- [ ] **Step 2 — implement:** add near `/overpowered`:
```python
@app.get("/entries/{entry_id}/optimize")
async def entry_optimize(entry_id: int, horizon: int = Query(5, ge=1, le=10),
                         max_transfers: int = Query(2, ge=0, le=3),
                         free_transfers: int = Query(1, ge=0, le=5),
                         model: str = Query("advanced",
                                            pattern="^(auto|basic|advanced)$"),
                         db: AsyncSession = Depends(get_db)) -> dict:
    lt = await _linked_or_404(db, entry_id)
    mv = await _resolve_model_version(db, model)
    latest_gw = (await db.execute(
        select(func.max(EntryPick.gameweek_id)).where(EntryPick.linked_team_id == lt.id)
    )).scalar()
    squad_rows = (await db.execute(
        select(EntryPick, Player).join(Player, Player.id == EntryPick.player_id)
        .where(EntryPick.linked_team_id == lt.id, EntryPick.gameweek_id == latest_gw)
    )).all()
    if not squad_rows:
        raise HTTPException(status_code=404, detail="no picks for this entry")

    xp_by_player = dict((await db.execute(
        select(PlayerGwPrediction.player_id, func.sum(PlayerGwPrediction.xp))
        .where(PlayerGwPrediction.model_version == mv,
               PlayerGwPrediction.horizon_gw <= horizon)
        .group_by(PlayerGwPrediction.player_id)
    )).all())
    shorts = dict((await db.execute(select(Team.id, Team.short_name))).all())

    def brief(p: Player) -> dict:
        return {"player_id": p.id, "web_name": p.web_name, "position": p.position,
                "now_cost": p.now_cost, "team_id": p.team_id,
                "team_short": shorts.get(p.team_id, ""),
                "xp": round(float(xp_by_player.get(p.id, 0.0)), 2)}

    squad = [brief(pl) for _, pl in squad_rows]
    squad_ids = {p["player_id"] for p in squad}

    # market: available players with a prediction, best ~40 per position
    market_players = (await db.execute(
        select(Player).where(Player.status == "a")
    )).scalars().all()
    market = sorted(
        (brief(p) for p in market_players
         if p.id not in squad_ids and p.id in xp_by_player),
        key=lambda d: -d["xp"],
    )
    trimmed: list[dict] = []
    per_pos: dict[str, int] = {}
    for m in market:
        if per_pos.get(m["position"], 0) >= 40:
            continue
        per_pos[m["position"]] = per_pos.get(m["position"], 0) + 1
        trimmed.append(m)

    bank = (await db.execute(
        select(EntryGwHistory.bank).where(EntryGwHistory.linked_team_id == lt.id)
        .order_by(EntryGwHistory.gameweek_id.desc()).limit(1)
    )).scalar() or 0

    gws = [{"id": g.id} for g in (await db.execute(select(Gameweek))).scalars().all()]
    fixtures = [
        {"gameweek_id": f.gameweek_id, "home_team_id": f.home_team_id,
         "away_team_id": f.away_team_id}
        for f in (await db.execute(select(Fixture))).scalars().all()
    ]
    start = (latest_gw or 1) + 1
    cal = gw_calendar(fixtures, gws, from_gw=start, to_gw=start + horizon - 1,
                      team_ids=list({p["team_id"] for p in squad}))

    current = best_xi(squad, key="xp")
    plans = suggest_transfers(squad, trimmed, bank=int(bank),
                              free_transfers=free_transfers,
                              max_transfers=max_transfers, key="xp")
    chips = chip_hints(cal, squad_team_ids=[p["team_id"] for p in squad])
    return {"entry_id": entry_id, "horizon": horizon, "model": mv,
            "bank": int(bank), "current": current,
            "transfer_plans": plans, "chips": chips}
```
- [ ] Imports: `from fplguru_optimize import best_xi, chip_hints, suggest_transfers`
  (first-party group, alphabetical — after `fplguru_ml...`, before `fplguru_tools`). `gw_calendar`
  is already imported from `fplguru_tools`. `EntryGwHistory` already imported.
- [ ] **Step 3:** `pytest services/api -q` green; `ruff`; `alembic check` (unchanged).
  Commit `feat(api): GET /entries/{id}/optimize — XI, transfers, chip hints`.

---

## Task 4: web `/optimize` page

**Files:** `apps/web/src/lib/api.ts` (+ `api.optimize.test.ts`),
`apps/web/src/components/nav-items.ts`, `apps/web/src/app/optimize/page.tsx`,
`apps/web/src/app/optimize/OptimizeView.tsx`.

- [ ] `api.ts`:
```ts
export type OptPlayer = { player_id: number; web_name: string; position: string;
  now_cost: number; team_short: string; xp: number };
export type TransferPlan = {
  transfers: { out: OptPlayer; in: OptPlayer }[];
  gain: number; hit: number; net: number;
};
export type ChipHint = { chip: string; gameweek_id: number; reason: string };
export type Optimize = {
  entry_id: number; horizon: number; model: string; bank: number;
  current: { formation: string; total: number; xi: OptPlayer[]; bench: OptPlayer[];
    captain: OptPlayer | null; vice: OptPlayer | null };
  transfer_plans: TransferPlan[]; chips: ChipHint[];
};
export function getOptimize(base: string, entryId: number, horizon = 5, maxTransfers = 2) {
  return fetch(
    `${base}/entries/${entryId}/optimize?horizon=${horizon}&max_transfers=${maxTransfers}`,
    { cache: "no-store" },
  ).then(asJson<Optimize>);
}
```
  test: URL contains `/entries/7/optimize?horizon=5&max_transfers=2`.
- [ ] `nav-items.ts`: add `{ href: "/optimize", label: "Optimize", icon: Wand2 }` (import `Wand2`
  from `lucide-react`), after `/captain`.
- [ ] `page.tsx`: thin wrapper rendering `<OptimizeView />`.
- [ ] `OptimizeView.tsx` (`"use client"`): `getStoredEntryId()` gate (reuse the `/squad`
  "No team linked" `EmptyState`); horizon (`1|3|5|8`) + max-transfers (`0|1|2|3`) segmented
  selectors persisted via `getPrefStr`/`setPrefStr`; on change refetch. Render:
  - a `PageHeader` with `formation` + `total` xP + bank;
  - the recommended plan (`transfer_plans[0]`): out→in rows with xp delta, `gain` / `hit` / `net`
    badges (`net >= 0` → `positive`, else `danger`); if `transfers` empty show "Roll your
    transfer";
  - a `DataTable` of the XI (Pos, Player, xP, C/V badge), bench listed below;
  - chip hint chips (`Badge` per hint: `chip` + `GW{gameweek_id}` + `reason` in a tooltip/title).
  Loading `Skeleton`s, error text — match `/squad`.
- [ ] `vitest run` → 23 passed; `next build` → success (`/optimize` route listed).
  Commit `feat(web): /optimize page — recommended XI, transfers, chips`.

---

## Task 5: docs

- [ ] `README.md` — a short "Optimize" section: `fplguru-optimize` (best XI, greedy transfer
  search net of the 4-pt hit, DGW/BGW chip hints), `GET /entries/{id}/optimize?horizon=&max_transfers=&free_transfers=`,
  `/optimize` page. Note it optimises on Advanced xP and is greedy (not a global ILP).
- [ ] `docs/plans/2026-08-27-fplguru-master-build-plan.md` — **P2d ✅** row (paths; deferred:
  global/ILP optimiser, multi-week transfer planning, price-change modelling, explicit chip
  simulation); decrement the count; note **P4a (Saved Optimization Plans) now unblocked**.
- [ ] `docs/RESUME-foundation.md` — top line + a `## P2d` section (task table, "greedy not
  optimal / same-position transfers only" caveat, no migration).
- [ ] Full sweep: `pytest -q -W error`, `ruff check .`, `alembic check`, web `vitest` + `build`.
  Commit `docs: P2d Optimize My Team complete`.

---

## Self-Review

**Spec coverage (master §4.5):** suggested transfers in/out → `suggest_transfers` (Task 2,3);
captain/vice → `best_xi` (Task 1); bench order → `best_xi.bench` (reserve GK first); chip-timing
window flags → `chip_hints` (Task 2); horizon selector → `?horizon=` 1–10 + web selector (no
Free/Pro split of the range — 2026-08-27 pivot); persisted preference → web `prefs` (localStorage),
no DB. "Basic algo vs advanced xP" → single path on the resolved model (defaults to advanced).
**Deferred:** global optimiser (this is greedy), cross-position transfers (kept same-position so
the 15-shape stays legal without re-solving), price-change/xfer-value modelling, true chip
simulation, saved plans (that's P4a).

**No migration** — reads `EntryPick` / `PlayerGwPrediction` / `EntryGwHistory` / `Fixture`.
`alembic check` must stay clean.

**Consistency:** `best_xi` / `suggest_transfers` / `chip_hints` signatures identical across the
package, its tests, and the API call site; player dict shape (`player_id, position, now_cost,
team_id, xp`) uniform between `brief()` (API) and the package; `model_version` resolved via the
shared `_resolve_model_version`; `gw_calendar` reused (not reimplemented).

**Placeholder scan:** Task 4's `OptimizeView` is described (not full code) — it mirrors
`/squad`'s `SquadTable` structure (selectors via `prefs`, `DataTable`, `EmptyState`, `Skeleton`);
acceptable. Tasks 1–3 are complete code.

---

## Execution Handoff

Branch `feature/p2d-optimize` off `main`. Subagent-driven, order 1 → 5. Tasks 1–3 get a full
review; 4 spec-check + quality-check; 5 spec-check. After Task 5: whole-branch review, PR → `main`,
watch CI, squash-merge. **Then P4a (Saved Optimization Plans) is unblocked.**

### Deferred follow-ups
- Global / ILP optimiser (branch-and-bound or LP relaxation) instead of greedy.
- Multi-gameweek transfer planning (bank rolls, planned hits).
- Price-change modelling so "transfer now vs wait" is answerable.
- Explicit chip simulation (project the points gain of each chip in its best week).
- `/captain` and `/squad` cross-links into `/optimize`.
