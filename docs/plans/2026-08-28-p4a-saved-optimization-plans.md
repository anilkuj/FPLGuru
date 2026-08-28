# P4a — Saved Optimization Plans — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. TDD; gates `python -m pytest -q -W error` + `python -m ruff check .` + `python -m alembic check` (+ `vitest` / `next build` for the web task).

**Goal:** Let a linked team save the current `/optimize` result under a name, list its saved
plans, reopen one, and delete one. Capped per team (default 5, oldest evicted past the cap).

**Architecture:** One new table `optimization_plan` (migration `0013`) storing a JSON-text snapshot
of the optimizer output plus the params it was run with. `entry_optimize`'s body is factored into
`_run_optimize(...)` so the POST route reuses it to build the snapshot. Four routes under
`/entries/{id}/plans`. The `/optimize` web page gains a "Save plan" control and a saved-plans list
that reloads a snapshot into the view.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, Next.js. One migration (`0013`, one `create_table`,
a `Text` payload column — no JSON `server_default`). No new deps.

---

## Project context (read once)

- Branch **`feature/p4a-saved-plans`** off `main` (P2f merged).
- **`GET /entries/{entry_id}/optimize`** in `services/api/src/fplguru_api/main.py` — assembles
  squad + market + bank + calendar and returns
  `{entry_id, horizon, model, bank, current, transfer_plans, chips}` via
  `fplguru_optimize.{best_xi, suggest_transfers, chip_hints}`. **This body must be factored into a
  helper** so the POST route can reuse it.
- **Mutating-route rules** (learned): `get_db` is read-only and does NOT commit. A mutating route
  does its writes then `await db.commit()` — do NOT use `async with db.begin()` (the session
  autobegins on the first read). Capture any returned values before `commit()`.
- `_linked_or_404(db, entry_id) -> LinkedTeam`.
- **Alembic head `0012`** (plain string revisions). `packages/core/tests/test_models.py::
  test_expected_tables_registered` asserts the exact table-name set — add `optimization_plan`.
  A `Text`/`String` column with a Python-side default is `alembic check`-safe; JSON
  `server_default` is not.
- `_TimestampMixin` provides only `updated_at` (`server_default=now()`), not `created_at` — add an
  explicit `created_at` column (see `LlmCall` for the pattern:
  `DateTime(timezone=True), server_default=func.now(), index=True`).
- **Settings** `packages/core/src/fplguru_core/settings.py` — add `saved_plans_cap: int = 5`.
- **Web** `/optimize` = `apps/web/src/app/optimize/OptimizeView.tsx` (`"use client"`, horizon +
  max-transfers selectors via `getPref`/`setPref`, fetches `getOptimize`). `api.ts` `asJson<T>`.
  Primitives: `Button`, `Input`, `Card`, `Badge`, `Skeleton`.
- **Baseline:** `pytest -q` → **241 passed**; web `vitest run` → **28 passed**.
- **SAC:** pure Python only.

---

## Task 1: `optimization_plan` table (`0013`) + settings

**Files:** `packages/core/src/fplguru_core/models.py`,
`packages/core/src/fplguru_core/settings.py`, `alembic/versions/0013_optimization_plan.py`,
`packages/core/tests/test_models.py`.

- [ ] **Step 1 — model** (after `XpRationale`):
```python
class OptimizationPlan(_TimestampMixin, Base):
    """A named snapshot of an /optimize result for a linked team."""
    __tablename__ = "optimization_plan"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    linked_team_id: Mapped[int] = mapped_column(ForeignKey("linked_teams.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    horizon: Mapped[int] = mapped_column(Integer)
    max_transfers: Mapped[int] = mapped_column(Integer)
    model_version: Mapped[str] = mapped_column(String(16))
    payload: Mapped[str] = mapped_column(Text)   # json.dumps of the optimizer result
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
```
  (`Text` is imported in `models.py` already — verify; if not, add it to the sqlalchemy import.)

- [ ] **Step 2 — settings:** add `saved_plans_cap: int = 5` near the other ints.

- [ ] **Step 3 — migration `0013_optimization_plan.py`** (`revision='0013'`,
  `down_revision='0012'`): one `op.create_table('optimization_plan', ...)` with
  `id` BigInteger autoincrement PK (`pk_optimization_plan`), `linked_team_id` Integer +
  FK `fk_optimization_plan_linked_team_id_linked_teams` + index
  `ix_optimization_plan_linked_team_id`, `name` String(80), `horizon` Integer,
  `max_transfers` Integer, `model_version` String(16), `payload` Text,
  `created_at` DateTime(tz) `server_default=sa.text('now()')` + index
  `ix_optimization_plan_created_at`, `updated_at` DateTime(tz)
  `server_default=sa.text('now()')`. Matching `downgrade()` (drop indexes then table).

- [ ] **Step 4:** add `"optimization_plan"` to `test_expected_tables_registered`.
  `python -m alembic upgrade head` then `python -m alembic check` → "No new upgrade operations".
  `pytest packages/core -q` green. Commit `feat(core): optimization_plan table (0013)`.

---

## Task 2: plans CRUD API

**Files:** `services/api/src/fplguru_api/main.py`, `services/api/tests/test_saved_plans_api.py`.

- [ ] **Step 1 — factor** the `entry_optimize` body into:
```python
async def _run_optimize(db: AsyncSession, lt: LinkedTeam, *, horizon: int,
                        max_transfers: int, free_transfers: int, model: str) -> dict:
    ...  # everything currently inside entry_optimize after `lt = await _linked_or_404(...)`
    return {"entry_id": lt.fpl_entry_id, "horizon": horizon, "model": mv, "bank": int(bank),
            "current": ..., "transfer_plans": ..., "chips": ...}
```
  and make `entry_optimize` call it. Run `pytest services/api/tests/test_optimize_api.py -q` — must
  still pass unchanged.

- [ ] **Step 2 — failing test** `test_saved_plans_api.py` (seed like `test_optimize_api.py` +
  a `LinkedTeam`): 
  - `POST /entries/{id}/plans` body `{"name": "GW pre-DGW", "horizon": 2, "max_transfers": 1}`
    → 201, returns `{id, name, created_at, horizon, max_transfers, model, plan: {...}}` where
    `plan` is a full optimizer result (`current.xi` len 11).
  - `GET /entries/{id}/plans` → list with the one plan (summary: `id, name, created_at, horizon,
    max_transfers, model` — **no** `plan` blob).
  - `GET /entries/{id}/plans/{plan_id}` → the full stored `plan`.
  - `DELETE /entries/{id}/plans/{plan_id}` → 204, then `GET .../plans` is empty.
  - POST a 6th plan when `saved_plans_cap=5` (monkeypatch settings) → the oldest is evicted, list
    length stays 5.
  - `GET /entries/{id}/plans/{other_teams_plan_id}` → 404 (scoped to the linked team).
  - unlinked entry → 404.

- [ ] **Step 3 — implement** (after `entry_optimize`):
```python
class _PlanIn(BaseModel):
    name: str = "My plan"
    horizon: int = 5
    max_transfers: int = 2
    free_transfers: int = 1
    model: str = "advanced"


def _plan_summary(p: OptimizationPlan) -> dict:
    return {"id": p.id, "name": p.name, "created_at": p.created_at.isoformat(),
            "horizon": p.horizon, "max_transfers": p.max_transfers,
            "model": p.model_version}


@app.post("/entries/{entry_id}/plans", status_code=201)
async def create_plan(entry_id: int, body: _PlanIn,
                      db: AsyncSession = Depends(get_db)) -> dict:
    lt = await _linked_or_404(db, entry_id)
    h = max(1, min(10, body.horizon))
    mt = max(0, min(3, body.max_transfers))
    result = await _run_optimize(db, lt, horizon=h, max_transfers=mt,
                                 free_transfers=max(0, min(5, body.free_transfers)),
                                 model=body.model if body.model in
                                 ("auto", "basic", "advanced") else "advanced")
    plan = OptimizationPlan(linked_team_id=lt.id, name=body.name[:80], horizon=h,
                            max_transfers=mt, model_version=result["model"],
                            payload=json.dumps(result))
    db.add(plan)
    await db.flush()
    # enforce the cap: drop oldest beyond `saved_plans_cap`
    cap = get_settings().saved_plans_cap
    ids = (await db.execute(
        select(OptimizationPlan.id).where(OptimizationPlan.linked_team_id == lt.id)
        .order_by(OptimizationPlan.created_at.desc(), OptimizationPlan.id.desc())
    )).scalars().all()
    for stale in ids[cap:]:
        await db.execute(delete(OptimizationPlan).where(OptimizationPlan.id == stale))
    summary = _plan_summary(plan)
    await db.commit()
    return {**summary, "plan": result}


@app.get("/entries/{entry_id}/plans")
async def list_plans(entry_id: int, db: AsyncSession = Depends(get_db)) -> list[dict]:
    lt = await _linked_or_404(db, entry_id)
    rows = (await db.execute(
        select(OptimizationPlan).where(OptimizationPlan.linked_team_id == lt.id)
        .order_by(OptimizationPlan.created_at.desc(), OptimizationPlan.id.desc())
    )).scalars().all()
    return [_plan_summary(p) for p in rows]


@app.get("/entries/{entry_id}/plans/{plan_id}")
async def get_plan(entry_id: int, plan_id: int,
                   db: AsyncSession = Depends(get_db)) -> dict:
    lt = await _linked_or_404(db, entry_id)
    p = (await db.execute(
        select(OptimizationPlan).where(OptimizationPlan.id == plan_id,
                                       OptimizationPlan.linked_team_id == lt.id)
    )).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="plan not found")
    return {**_plan_summary(p), "plan": json.loads(p.payload)}


@app.delete("/entries/{entry_id}/plans/{plan_id}", status_code=204)
async def delete_plan(entry_id: int, plan_id: int,
                      db: AsyncSession = Depends(get_db)) -> None:
    lt = await _linked_or_404(db, entry_id)
    res = await db.execute(
        delete(OptimizationPlan).where(OptimizationPlan.id == plan_id,
                                       OptimizationPlan.linked_team_id == lt.id)
    )
    await db.commit()
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="plan not found")
```
- [ ] Imports: `from sqlalchemy import delete` (add to the existing sqlalchemy import line),
  `OptimizationPlan` from `fplguru_core.models`. `json` + `BaseModel` already imported.
- [ ] **Step 4:** `pytest services/api -q` green; `ruff`; `alembic check`.
  Commit `feat(api): saved optimization plans CRUD (/entries/{id}/plans)`.

---

## Task 3: web — save & reopen plans on /optimize

**Files:** `apps/web/src/lib/api.ts` (+ `api.plans.test.ts`),
`apps/web/src/app/optimize/OptimizeView.tsx`.

- [ ] `api.ts`:
```ts
export type PlanSummary = {
  id: number; name: string; created_at: string;
  horizon: number; max_transfers: number; model: string;
};
export type SavedPlan = PlanSummary & { plan: Optimize };
export function listPlans(base: string, entryId: number) {
  return fetch(`${base}/entries/${entryId}/plans`, { cache: "no-store" })
    .then(asJson<PlanSummary[]>);
}
export function createPlan(base: string, entryId: number,
                           body: { name: string; horizon: number; max_transfers: number }) {
  return fetch(`${base}/entries/${entryId}/plans`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  }).then(asJson<SavedPlan>);
}
export function getPlan(base: string, entryId: number, planId: number) {
  return fetch(`${base}/entries/${entryId}/plans/${planId}`, { cache: "no-store" })
    .then(asJson<SavedPlan>);
}
export async function deletePlan(base: string, entryId: number, planId: number) {
  const r = await fetch(`${base}/entries/${entryId}/plans/${planId}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`http ${r.status}`);
}
```
  test (`api.plans.test.ts`): `createPlan` POSTs JSON to `/entries/7/plans`; `deletePlan` issues a
  `DELETE` and throws on `!ok`.
- [ ] `OptimizeView.tsx`:
  - after data loads, a "Save plan" `Button` → prompt/inline `Input` for a name (default
    `GW·{horizon} · {new Date().toLocaleDateString()}`) → `createPlan(...)` with the current
    `horizon` / `maxT` → refresh the saved list.
  - a "Saved plans" `Card`: `listPlans` on mount + after save/delete; each row = name + relative
    date + "Open" (calls `getPlan`, sets `data` to `plan`, and syncs `horizon`/`maxT` from the
    summary) + "Delete" (`deletePlan` → refresh). Empty → a muted "No saved plans yet."
  - guard the whole block on `entryId` being set (it already gates the page).
- [ ] `vitest run` → 30 passed; `next build` → success.
  Commit `feat(web): save & reopen optimization plans`.

---

## Task 4: docs

- [ ] `README.md` — extend the Optimize section: plans are saved snapshots of an `/optimize`
  result; `POST/GET/DELETE /entries/{id}/plans[/{plan_id}]`; capped at `saved_plans_cap` (default
  5, oldest evicted); the `/optimize` page saves & reopens them.
- [ ] `docs/plans/2026-08-27-fplguru-master-build-plan.md` — **P4a ✅** row; the count line goes to
  **2** (only P3/P1a-auth families remain, all key/decision-blocked); deferred: plan diffing,
  auto-snapshot each GW, share links.
- [ ] `docs/RESUME-foundation.md` — top line + a `## P4a` section (task table; "payload is a
  JSON-text blob, not queried; cap evicts oldest"; migration `0013`).
- [ ] Full sweep: `pytest -q -W error`, `ruff check .`, `alembic check`, web `vitest` + `build`.
  Commit `docs: P4a Saved Optimization Plans complete`.

---

## Self-Review

**Spec coverage (§4.5 / §3):** "up to 5 saved plans" → `saved_plans_cap` (default 5, evict oldest);
"per Pro user" → per linked team, no Pro gate (2026-08-27 pivot). CRUD covers save / list / reopen
/ delete. Plans are scoped to the linked team (cross-team access → 404).

**Migration:** one `create_table` (`0013`), `Text` payload (no JSON `server_default`) → `alembic
check` clean; models exact-set test updated. Explicit `created_at` (mixin only gives `updated_at`).

**Consistency:** `_run_optimize` returns exactly the dict `entry_optimize` returned before (so the
existing `test_optimize_api.py` passes untouched); `_plan_summary` shape identical in POST / list /
get and matches the web `PlanSummary` type; `payload` round-trips `json.dumps` ↔ `json.loads`;
mutating routes use `await db.commit()` (not `db.begin()`).

**Placeholder scan:** Task 3 `OptimizeView` changes are described against the existing component;
Tasks 1–2 are complete code (Task 2 Step 1 is a pure extract-method with a behaviour-preserving
check). No undefined types.

---

## Execution Handoff

Branch `feature/p4a-saved-plans` off `main`. Subagent-driven, order 1 → 4. Tasks 1 & 2 get a full
review; 3 spec-check + quality-check; 4 spec-check. After Task 4: whole-branch review, PR → `main`,
watch CI, squash-merge. **This is the last unblocked master-plan sub-plan** — after it, only the
key/decision-blocked P3a–d and P1a-auth remain.

### Deferred follow-ups
- Plan diffing (what changed vs the last saved plan / vs the live optimum).
- Auto-snapshot a plan each gameweek for a personal history.
- Shareable read-only plan links.
- Store the squad-at-time-of-plan so a reopened plan can show drift.
