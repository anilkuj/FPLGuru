# P2f — H2H Match Helper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. TDD; gates `python -m pytest -q -W error` + `python -m ruff check .` + `python -m alembic check` (+ `vitest` / `next build` for the web task).

**Goal:** Given your linked team and any opponent's FPL entry id, show a squad-vs-squad view:
each side's best XI + captain on Advanced xP, the differentials (players only one side owns) and
their xP, the projected points margin, captain divergence, and a plain-English strategy suggestion.

**Architecture:** A new **pure** package `fplguru-h2h` — `compare_squads(mine, theirs, *, horizon)`
returns the diff/overlap/margin/captain analysis and a `template_strategy` string; it reuses
`fplguru_optimize.best_xi` for each side's XI. A read endpoint `GET
/entries/{id}/h2h/{opponent_id}` syncs the opponent via the existing `sync_entry`, loads both
squads + horizon-summed predictions, and calls the package. A new `/h2h` web page takes an opponent
id and renders it. No LLM call in v1 (template strategy only — budget-safe). No migration.

**Tech Stack:** pure Python, FastAPI, Next.js. No new deps, no migration.

---

## Project context (read once)

- Branch **`feature/p2f-h2h`** off `main` (P4b merged).
- **`fplguru_entrysync.sync_entry(entry_id) -> int`** — fetches an FPL entry, upserts its
  `LinkedTeam` + `EntryGwHistory` + latest-finished-GW `EntryPick` rows, returns the
  `linked_team_id`. Idempotent. Already used by `POST /link/{id}`. Safe to call for an opponent.
- **`fplguru_optimize.best_xi(squad, key="xp") -> {formation, total, xi, bench, captain, vice}`**
  (captain = top XI xP, vice = 2nd). Player dicts need `player_id, position, now_cost, team_id, xp`.
- **API** `services/api/src/fplguru_api/main.py`: `_linked_or_404(db, entry_id) -> LinkedTeam`;
  `_resolve_model_version(db, model="auto")`; `GET /entries/{id}` shows the pattern for
  latest-pick-GW + `xp_by_player = sum(PlayerGwPrediction.xp)` grouped by player for a
  `model_version`. `EntryPick(linked_team_id, gameweek_id, player_id, slot, is_captain, is_vice)`.
- **Web** page pattern: `src/app/<route>/page.tsx` (thin) → `"use client"` child. `api.ts`
  `asJson<T>`, `XpModel`. `getStoredEntryId()`. Primitives: `Card`, `Badge`, `DataTable`,
  `Input`, `Button`, `PageHeader`, `EmptyState`, `Skeleton`. `nav-items.ts` `NAV_ITEMS`.
- **Baseline:** `pytest -q` → **235 passed**; web `vitest run` → **26 passed**.
- **SAC:** pure Python only.

---

## Task 1: `fplguru-h2h` package

**Files:** create `packages/h2h/pyproject.toml`, `packages/h2h/src/fplguru_h2h/__init__.py`,
`packages/h2h/tests/test_h2h.py`; edit root `pyproject.toml` (`known-first-party` → add
`fplguru_h2h`), `requirements-dev.txt` (`-e ./packages/h2h`).

- [ ] **Step 1 — `pyproject.toml`** (copy `packages/optimize/pyproject.toml`, s/optimize/h2h/,
  `description = "Pure head-to-head squad comparison."`).

- [ ] **Step 2 — failing test** `test_h2h.py`:
```python
from fplguru_h2h import compare_squads


def _p(pid, pos, xp, club=1):
    return {"player_id": pid, "web_name": f"P{pid}", "position": pos,
            "now_cost": 50, "team_id": club, "xp": xp}


def _full(base, xp_map):
    s, pid = [], base
    for pos, n in (("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)):
        for _ in range(n):
            s.append(_p(pid, pos, xp_map.get(pid, 10.0)))
            pid += 1
    return s


def test_compare_reports_margin_diffs_and_captains():
    mine = _full(1, {3: 30.0})       # my DEF id 3 is elite
    theirs = _full(1, {})            # identical ids -> full overlap, then override two
    theirs[7] = _p(99, "DEF", 25.0)  # they own id 99, I don't
    theirs[8] = _p(98, "MID", 5.0)
    r = compare_squads(mine, theirs, horizon=3)
    assert r["your_xi_total"] > 0 and r["their_xi_total"] > 0
    assert round(r["margin"], 2) == round(r["your_xi_total"] - r["their_xi_total"], 2)
    assert 99 in {p["player_id"] for p in r["their_differentials"]}
    assert 3 in {p["player_id"] for p in r["your_differentials"]}
    assert r["your_captain"]["player_id"] == 3          # elite DEF tops my XI
    assert isinstance(r["shared_count"], int) and r["shared_count"] > 0
    assert isinstance(r["strategy"], str) and r["strategy"]


def test_strategy_text_switches_on_who_leads():
    a = _full(1, {})
    ahead = compare_squads(_full(1, {3: 60.0}), a, horizon=1)
    behind = compare_squads(a, _full(1, {3: 60.0}), horizon=1)
    assert "ahead" in ahead["strategy"].lower()
    assert "behind" in behind["strategy"].lower()
```

- [ ] **Step 3 — implement `__init__.py`:**
```python
"""Pure head-to-head squad comparison (no DB, no network)."""
from __future__ import annotations

from typing import Any

from fplguru_optimize import best_xi

__all__ = ["compare_squads", "template_strategy"]


def _brief(p: dict) -> dict:
    return {"player_id": p["player_id"], "web_name": p.get("web_name", ""),
            "position": p["position"], "xp": round(float(p.get("xp", 0.0)), 2)}


def template_strategy(margin: float, *, same_captain: bool,
                      their_diffs: list[dict]) -> str:
    top_threat = max(their_diffs, key=lambda p: p["xp"], default=None)
    threat = (f" Watch {top_threat['web_name']} ({top_threat['xp']} xP) — their best "
              f"player you don't own." if top_threat and top_threat["xp"] > 3 else "")
    if margin >= 3:
        return (f"You're ahead by ~{margin:.1f} projected pts. Play the percentages: "
                f"match their captain and avoid needless risk.{threat}")
    if margin <= -3:
        return (f"You're behind by ~{abs(margin):.1f} projected pts. Consider a "
                f"differential captain or an aggressive transfer to create swing.{threat}")
    cap = "Your captains match — the bench and differentials decide this one." if same_captain \
        else "Close on paper; your captain call is the likely swing."
    return f"Roughly level (within {abs(margin):.1f} pts). {cap}{threat}"


def compare_squads(mine: list[dict[str, Any]], theirs: list[dict[str, Any]], *,
                   horizon: int) -> dict:
    my_xi = best_xi(mine, key="xp")
    their_xi = best_xi(theirs, key="xp")
    my_ids = {p["player_id"] for p in mine}
    their_ids = {p["player_id"] for p in theirs}
    shared = my_ids & their_ids
    your_diffs = sorted((_brief(p) for p in mine if p["player_id"] not in their_ids),
                        key=lambda p: -p["xp"])
    their_diffs = sorted((_brief(p) for p in theirs if p["player_id"] not in my_ids),
                         key=lambda p: -p["xp"])
    margin = round(my_xi["total"] - their_xi["total"], 2)
    same_cap = bool(my_xi["captain"] and their_xi["captain"]
                    and my_xi["captain"]["player_id"] == their_xi["captain"]["player_id"])
    return {
        "horizon": horizon,
        "your_xi_total": my_xi["total"], "their_xi_total": their_xi["total"],
        "margin": margin,
        "your_captain": _brief(my_xi["captain"]) if my_xi["captain"] else None,
        "their_captain": _brief(their_xi["captain"]) if their_xi["captain"] else None,
        "same_captain": same_cap,
        "shared_count": len(shared),
        "your_differentials": your_diffs,
        "their_differentials": their_diffs,
        "strategy": template_strategy(margin, same_captain=same_cap,
                                      their_diffs=their_diffs),
    }
```

- [ ] **Step 4:** wire `known-first-party` + `requirements-dev.txt`; `pip install -e ./packages/h2h`;
  `pytest packages/h2h -q` green; `ruff` clean.
  Commit `feat(h2h): fplguru-h2h squad-vs-squad comparison`.

---

## Task 2: `GET /entries/{id}/h2h/{opponent_id}`

**Files:** `services/api/src/fplguru_api/main.py`, `services/api/tests/test_h2h_api.py`.

- [ ] **Step 1 — failing test** `test_h2h_api.py`: seed my `LinkedTeam` (id 1, entry 77) + a full
  15 `EntryPick` at the latest GW; seed an opponent `LinkedTeam` (id 2, entry 88) + its 15 picks
  (share ~11, differ on 4); `Player`/`Team` rows; `adv-v1` `PlayerGwPrediction` over 2 horizons.
  Monkeypatch `fplguru_api.main.sync_entry` to a stub `async def _stub(eid): return 2` (so the test
  doesn't hit the network). Assert:
  - `GET /entries/77/h2h/88?horizon=2` → 200; body has `opponent_entry_id == 88`,
    `your_xi_total` / `their_xi_total` / `margin`, `your_differentials` + `their_differentials`
    lists, `strategy` non-empty, `model == "adv-v1"`.
  - my entry unlinked → 404 (before touching the opponent).
  - opponent with no picks after sync → 404 "opponent has no squad".

- [ ] **Step 2 — implement** (near `/entries/{id}/optimize`):
```python
@app.get("/entries/{entry_id}/h2h/{opponent_id}")
async def entry_h2h(entry_id: int, opponent_id: int,
                    horizon: int = Query(5, ge=1, le=10),
                    model: str = Query("advanced", pattern="^(auto|basic|advanced)$"),
                    db: AsyncSession = Depends(get_db)) -> dict:
    lt = await _linked_or_404(db, entry_id)
    mv = await _resolve_model_version(db, model)
    try:
        await sync_entry(opponent_id)
    except Exception as exc:   # opponent id invalid / FPL unreachable
        raise HTTPException(status_code=502, detail="could not fetch opponent") from exc
    opp = (await db.execute(
        select(LinkedTeam).where(LinkedTeam.fpl_entry_id == opponent_id)
    )).scalar_one_or_none()
    if opp is None:
        raise HTTPException(status_code=404, detail="opponent not found")

    xp_by_player = dict((await db.execute(
        select(PlayerGwPrediction.player_id, func.sum(PlayerGwPrediction.xp))
        .where(PlayerGwPrediction.model_version == mv,
               PlayerGwPrediction.horizon_gw <= horizon)
        .group_by(PlayerGwPrediction.player_id)
    )).all())

    async def squad(team_id: int) -> list[dict]:
        latest = (await db.execute(
            select(func.max(EntryPick.gameweek_id))
            .where(EntryPick.linked_team_id == team_id)
        )).scalar()
        rows = (await db.execute(
            select(Player).join(EntryPick, EntryPick.player_id == Player.id)
            .where(EntryPick.linked_team_id == team_id, EntryPick.gameweek_id == latest)
        )).scalars().all()
        return [{"player_id": p.id, "web_name": p.web_name, "position": p.position,
                 "now_cost": p.now_cost, "team_id": p.team_id,
                 "xp": round(float(xp_by_player.get(p.id, 0.0)), 2)} for p in rows]

    mine = await squad(lt.id)
    theirs = await squad(opp.id)
    if not mine:
        raise HTTPException(status_code=404, detail="no picks for this entry")
    if not theirs:
        raise HTTPException(status_code=404, detail="opponent has no squad")

    return {"entry_id": entry_id, "opponent_entry_id": opponent_id,
            "opponent_name": opp.manager_name, "model": mv,
            **compare_squads(mine, theirs, horizon=horizon)}
```
- [ ] Imports: `from fplguru_h2h import compare_squads` (first-party group, before
  `fplguru_llm`/`fplguru_ml`... alphabetical: `fplguru_h2h` after `fplguru_fdr`/`fplguru_explain`
  — let ruff sort). `sync_entry` and `LinkedTeam` are already imported.
- [ ] **Step 3:** `pytest services/api -q` green; `ruff`; `alembic check` (unchanged).
  Commit `feat(api): GET /entries/{id}/h2h/{opponent_id} — squad-vs-squad`.

---

## Task 3: web `/h2h` page

**Files:** `apps/web/src/lib/api.ts` (+ `api.h2h.test.ts`),
`apps/web/src/components/nav-items.ts`, `apps/web/src/app/h2h/page.tsx`,
`apps/web/src/app/h2h/H2HView.tsx`.

- [ ] `api.ts`:
```ts
export type H2HPlayer = { player_id: number; web_name: string; position: string; xp: number };
export type H2H = {
  entry_id: number; opponent_entry_id: number; opponent_name: string; model: string;
  horizon: number; your_xi_total: number; their_xi_total: number; margin: number;
  your_captain: H2HPlayer | null; their_captain: H2HPlayer | null; same_captain: boolean;
  shared_count: number; your_differentials: H2HPlayer[]; their_differentials: H2HPlayer[];
  strategy: string;
};
export function getH2H(base: string, entryId: number, opponentId: number, horizon = 5) {
  return fetch(`${base}/entries/${entryId}/h2h/${opponentId}?horizon=${horizon}`,
    { cache: "no-store" }).then(asJson<H2H>);
}
```
  test: URL contains `/entries/7/h2h/42?horizon=5`.
- [ ] `nav-items.ts`: add `{ href: "/h2h", label: "H2H", icon: Swords }` (import `Swords`), after
  `/leagues`.
- [ ] `page.tsx`: thin → `<H2HView />`.
- [ ] `H2HView.tsx` (`"use client"`): `getStoredEntryId()` gate; an `Input` for the opponent entry
  id + a "Compare" `Button` (persist last opponent via `setPrefStr`); on submit `getH2H`. Render:
  - a header line: `margin` as a big signed number with `Badge` (`positive` if ≥ 0 else `danger`),
    "you {your_xi_total} · {opponent_name} {their_xi_total}";
  - `strategy` in a `Card`;
  - captains: two chips, highlight if `same_captain`;
  - two `DataTable`s side by side (`sm:grid-cols-2`): "Your differentials" and "Their
    differentials" (Player, Pos, xP);
  - `shared_count` as a muted line.
  Loading `Skeleton`, error text (e.g. 502 → "Couldn't fetch that opponent — check the id").
- [ ] `vitest run` → 27 passed; `next build` → success (`/h2h` route).
  Commit `feat(web): /h2h match helper page`.

---

## Task 4: docs

- [ ] `README.md` — an "H2H Match Helper" section: `fplguru-h2h` (best-XI margin, differentials,
  captain divergence, template strategy), `GET /entries/{id}/h2h/{opponent_id}?horizon=&model=`
  (syncs the opponent via `sync_entry`), `/h2h` page. Note: template strategy only in v1 — an LLM
  strategy is a follow-up.
- [ ] `docs/plans/2026-08-27-fplguru-master-build-plan.md` — **P2f ✅** row; decrement the count;
  deferred: LLM strategy, bench/auto-sub modelling, live in-GW H2H tracking, H2H-league auto-pairing.
- [ ] `docs/RESUME-foundation.md` — top line + a `## P2f` section (task table; "opponent is synced
  into `linked_teams` on lookup — harmless, `/link` stays idempotent"; no migration).
- [ ] Full sweep: `pytest -q -W error`, `ruff check .`, `alembic check`, web `vitest` + `build`.
  Commit `docs: P2f H2H Match Helper complete`.

---

## Self-Review

**Spec coverage (§4.12):** opponent squad profiling → `squad()` + `sync_entry` (Task 2);
squad-vs-squad view → `compare_squads` + the `/h2h` page (Tasks 1,3); strategy suggestion →
`template_strategy` (Task 1). No Pro gate (2026-08-27 pivot). **Deferred:** LLM-written strategy
(budget-guarded, would need a cache table), bench/auto-sub simulation, live in-gameweek tracking.

**No migration** — `sync_entry` reuses existing `linked_teams`/`entry_picks`/`entry_gw_history`.
`alembic check` stays clean.

**Consistency:** `compare_squads` return shape identical across its tests, the API spread, and the
web `H2H` type; player-dict shape (`player_id, web_name, position, xp`) uniform; `best_xi` reused
(not reimplemented); `model_version` via `_resolve_model_version`.

**Placeholder scan:** Task 3 `H2HView` is described against the established page pattern
(`/squad`, `/optimize`); Task 2's `squad()` inner helper mirrors `/entries/{id}` / `/optimize`.
Tasks 1–2 are complete code.

**Risk:** the endpoint calls `sync_entry` (network) on every request. Acceptable for a
user-triggered comparison; the test monkeypatches it. A short-TTL skip ("synced < 10 min ago →
don't re-fetch") is a reasonable follow-up but not required.

---

## Execution Handoff

Branch `feature/p2f-h2h` off `main`. Subagent-driven, order 1 → 4. Tasks 1 & 2 get a full review;
3 spec-check + quality-check; 4 spec-check. After Task 4: whole-branch review, PR → `main`, watch
CI, squash-merge.

### Deferred follow-ups
- LLM-written strategy via `generate_within_budget` (needs a small `h2h_note` cache table).
- Bench / auto-substitution modelling in the margin.
- Live in-gameweek H2H score tracking.
- Auto-pair opponents from the manager's H2H leagues (needs the H2H-league endpoints).
- Short-TTL guard so repeated `/h2h` calls don't re-`sync_entry` the opponent.
