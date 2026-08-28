# P4b — Model Transparency Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. TDD; gates `python -m pytest -q -W error` + `python -m ruff check .` + `python -m alembic check` (+ `vitest` / `next build` for the web task).

**Goal:** A public view of how the xP models are actually doing: last finished GW's projection vs
actual points per player, and rolling MAE / RMSE / bias per position for **both** model versions
side by side (A/B).

**Architecture:** Pure `fplguru_ml.eval.pointwise_metrics` computes `{n, mae, rmse, bias}` from
`(pred, actual)` pairs. A read endpoint `GET /model/transparency` joins the stored
`PlayerGwPrediction` (`horizon_gw = 1` — the projection last computed for that GW) to actual
`PlayerGwStat.total_points` over the finished GWs, and returns per-model / per-position metrics
(overall + rolling last-N) plus a "last GW" breakdown. A new **Model** tab on the existing `/tools`
page renders it. No migration — the current `PlayerGwPrediction` rows for a finished GW are its
last pre-finish projection (the worker only writes predictions for *unfinished* GWs, so they are
not overwritten afterwards).

**Tech Stack:** numpy, FastAPI, Next.js. No new deps, no migration.

---

## Project context (read once)

- Branch **`feature/p4b-transparency`** off `main` (P2d merged at `fa7fa6a`).
- **`fplguru_ml.backtest`** already computes `mae` / `rmse` inline
  (`err.abs().mean()`, `sqrt((err**2).mean())`) — mirror that.
- **Models:** `PlayerGwPrediction(player_id, gameweek_id, horizon_gw, model_version, xp, ...)`
  unique on `(player_id, gameweek_id, model_version)`; `PlayerGwStat(player_id, gameweek_id,
  minutes, total_points, ...)` unique on `(player_id, gameweek_id)`; `Gameweek(id, finished,
  deadline_time)`; `Player(id, web_name, position ∈ {GK,DEF,MID,FWD})`.
- **API** `services/api/src/fplguru_api/main.py`: `_MODEL_VERSION="basic-v1"`,
  `_ADV_MODEL_VERSION="adv-v1"`; `get_db` read-only; `select` / `func` from sqlalchemy already
  imported. `_player_dicts` helper. Route style: `@app.get(...)` + `db: AsyncSession =
  Depends(get_db)`.
- **Worker** writes predictions only for `Gameweek.finished.is_(False)` (see
  `compute_and_store_xp`), so a finished GW keeps the last projection written before it finished.
  `horizon_gw = 1` is the "this GW" projection.
- **Web** `/tools` = `apps/web/src/app/tools/ToolsHub.tsx` — a `Tabs` component with tabs
  `trends|template|calendar|op|xg`, each lazy-fetching in a `useEffect` keyed on `tab`. Add a
  `model` tab the same way. `api.ts` has the `asJson<T>` helper + typed `get*` functions.
  `DataTable`, `Card`, `Badge`, `Select` primitives available.
- **Baseline:** `pytest -q` → **230 passed**; web `vitest run` → **24 passed**.
- **SAC:** pure Python/numpy only.

---

## Task 1: `fplguru_ml.eval.pointwise_metrics`

**Files:** `packages/ml/src/fplguru_ml/eval.py`, `packages/ml/tests/test_eval.py`.

- [ ] **Step 1 — failing test** `test_eval.py`:
```python
import math

from fplguru_ml.eval import pointwise_metrics


def test_metrics_on_known_pairs():
    # preds vs actuals: errors -1, +1, 0, +2
    m = pointwise_metrics([(4, 5), (6, 5), (3, 3), (7, 5)])
    assert m["n"] == 4
    assert math.isclose(m["mae"], (1 + 1 + 0 + 2) / 4)
    assert math.isclose(m["rmse"], math.sqrt((1 + 1 + 0 + 4) / 4))
    assert math.isclose(m["bias"], (-1 + 1 + 0 + 2) / 4)  # mean(pred - actual)


def test_metrics_empty_is_zeroed():
    m = pointwise_metrics([])
    assert m == {"n": 0, "mae": 0.0, "rmse": 0.0, "bias": 0.0}
```

- [ ] **Step 2 — implement `eval.py`:**
```python
"""Point-prediction accuracy metrics (projection vs actual)."""
from __future__ import annotations

from collections.abc import Iterable

import numpy as np


def pointwise_metrics(pairs: Iterable[tuple[float, float]]) -> dict:
    """`pairs` = (predicted, actual). Returns n / mae / rmse / bias (mean signed
    error, pred - actual). Empty input returns a zeroed dict."""
    arr = np.array([(float(p), float(a)) for p, a in pairs], dtype=float)
    if arr.size == 0:
        return {"n": 0, "mae": 0.0, "rmse": 0.0, "bias": 0.0}
    err = arr[:, 0] - arr[:, 1]
    return {
        "n": int(len(err)),
        "mae": float(np.abs(err).mean()),
        "rmse": float(np.sqrt((err ** 2).mean())),
        "bias": float(err.mean()),
    }
```

- [ ] **Step 3:** `pytest packages/ml/tests/test_eval.py -q` green; `ruff` clean.
  Commit `feat(ml): pointwise_metrics (mae / rmse / bias)`.

---

## Task 2: `GET /model/transparency`

**Files:** `services/api/src/fplguru_api/main.py`, `services/api/tests/test_transparency_api.py`.

- [ ] **Step 1 — failing test** `test_transparency_api.py`: seed `Gameweek` 1–3 (`finished=True`),
  `Player` rows across positions, `PlayerGwStat` (actual `total_points`) and
  `PlayerGwPrediction` (`horizon_gw=1`) for both `basic-v1` and `adv-v1` across those GWs. Assert:
  - `GET /model/transparency?last=2` → 200; body has `models` == `["basic-v1", "adv-v1"]`;
    `by_position` keyed by model → position → `{n, mae, rmse, bias}`;
    `rolling` (last-`last` GWs) present with the same shape;
    `last_gw.gameweek_id` == 3 and `last_gw.rows` sorted by `abs(delta)` desc, each
    `{player_id, web_name, position, model, predicted, actual, delta}`.
  - empty DB → 200 with `models` still `["basic-v1","adv-v1"]`, all-zero metrics, `last_gw` null.

- [ ] **Step 2 — implement** (add near `/overpowered`):
```python
@app.get("/model/transparency")
async def model_transparency(last: int = Query(6, ge=1, le=19),
                             db: AsyncSession = Depends(get_db)) -> dict:
    finished = [g for (g,) in (await db.execute(
        select(Gameweek.id).where(Gameweek.finished.is_(True)).order_by(Gameweek.id)
    )).all()]
    models = [_MODEL_VERSION, _ADV_MODEL_VERSION]
    empty = {"n": 0, "mae": 0.0, "rmse": 0.0, "bias": 0.0}
    if not finished:
        return {"models": models, "gameweeks": [], "by_position": {}, "rolling": {},
                "last_gw": None, "rolling_window": last}

    actual = {(pid, gw): tp for pid, gw, tp in (await db.execute(
        select(PlayerGwStat.player_id, PlayerGwStat.gameweek_id, PlayerGwStat.total_points)
        .where(PlayerGwStat.gameweek_id.in_(finished))
    )).all()}
    pos = dict((await db.execute(select(Player.id, Player.position))).all())
    names = dict((await db.execute(select(Player.id, Player.web_name)).all()) if False else
                 (await db.execute(select(Player.id, Player.web_name))).all())
    preds = (await db.execute(
        select(PlayerGwPrediction.player_id, PlayerGwPrediction.gameweek_id,
               PlayerGwPrediction.model_version, PlayerGwPrediction.xp)
        .where(PlayerGwPrediction.gameweek_id.in_(finished),
               PlayerGwPrediction.horizon_gw == 1,
               PlayerGwPrediction.model_version.in_(models))
    )).all()

    recent = set(finished[-last:])
    # buckets[model][position] -> list[(pred, actual)]; "ALL" position too
    buckets: dict = {m: {} for m in models}
    roll: dict = {m: {} for m in models}
    for pid, gw, mv, xp in preds:
        if (pid, gw) not in actual:
            continue
        p = pos.get(pid)
        if p is None:
            continue
        pair = (float(xp), float(actual[(pid, gw)]))
        for key in (p, "ALL"):
            buckets[mv].setdefault(key, []).append(pair)
            if gw in recent:
                roll[mv].setdefault(key, []).append(pair)

    def metric_map(src: dict) -> dict:
        return {mv: {k: pointwise_metrics(v) for k, v in src.get(mv, {}).items()}
                for mv in models}

    last_id = finished[-1]
    last_rows = []
    for pid, gw, mv, xp in preds:
        if gw != last_id or (pid, gw) not in actual:
            continue
        a = float(actual[(pid, gw)])
        last_rows.append({"player_id": pid, "web_name": names.get(pid, ""),
                          "position": pos.get(pid, ""), "model": mv,
                          "predicted": round(float(xp), 2), "actual": a,
                          "delta": round(float(xp) - a, 2)})
    last_rows.sort(key=lambda r: -abs(r["delta"]))
    return {
        "models": models, "gameweeks": finished, "rolling_window": last,
        "by_position": metric_map(buckets),
        "rolling": metric_map(roll),
        "last_gw": {"gameweek_id": last_id, "rows": last_rows[:40]} if last_rows else None,
        "_empty": empty,  # (drop; kept only if a caller needs the zero shape)
    }
```
  Clean up the obvious cruft above when implementing: `names` should just be
  `names = dict((await db.execute(select(Player.id, Player.web_name))).all())`; drop the `_empty`
  key from the response (it's not needed — `pointwise_metrics([])` already yields the zero shape).

- [ ] **Step 3:** `pytest services/api -q` green; `ruff`; `alembic check` (unchanged).
  Commit `feat(api): GET /model/transparency — projection vs actual, MAE/RMSE per model`.

---

## Task 3: web — "Model" tab on /tools

**Files:** `apps/web/src/lib/api.ts` (+ `api.transparency.test.ts`),
`apps/web/src/app/tools/ToolsHub.tsx`.

- [ ] `api.ts`:
```ts
export type ModelMetric = { n: number; mae: number; rmse: number; bias: number };
export type Transparency = {
  models: string[];
  gameweeks: number[];
  rolling_window: number;
  by_position: Record<string, Record<string, ModelMetric>>;
  rolling: Record<string, Record<string, ModelMetric>>;
  last_gw: {
    gameweek_id: number;
    rows: {
      player_id: number; web_name: string; position: string; model: string;
      predicted: number; actual: number; delta: number;
    }[];
  } | null;
};
export function getTransparency(base: string, last = 6) {
  return fetch(`${base}/model/transparency?last=${last}`, { cache: "no-store" })
    .then(asJson<Transparency>);
}
```
  test: URL contains `/model/transparency?last=6`.
- [ ] `ToolsHub.tsx`: add `<TabsTrigger value="model">Model</TabsTrigger>`, a
  `const [tr, setTr] = useState<Transparency | null>(null)`, a `useEffect` that fetches when
  `tab === "model" && !tr`, and a `<TabsContent value="model">` with:
  - a small table per model: rows = positions `GK/DEF/MID/FWD/ALL`, cols = `n`, `MAE`, `RMSE`,
    `bias` — from `by_position[model]`; a compact "rolling last {rolling_window}" table beside or
    below it from `rolling[model]`. Two models shown side by side (`sm:grid-cols-2`).
  - the `last_gw` block: `DataTable` of `rows` (Player, Pos, Model, Proj, Actual, Δ with a
    `Badge variant={delta >= 0 ? "positive" : "danger"}`), title `GW{gameweek_id} — projection vs
    actual`.
  - if `last_gw` is null / all `n` are 0: an `EmptyState` "No finished gameweeks with predictions
    yet."
- [ ] `vitest run` → 25 passed; `next build` → success.
  Commit `feat(web): Model accuracy tab on /tools`.

---

## Task 4: docs

- [ ] `README.md` — under the xP section, a "Transparency" note: `GET /model/transparency?last=N`
  compares the last-computed `horizon_gw=1` projection to actual points over finished GWs → MAE /
  RMSE / bias per position for `basic-v1` and `adv-v1`; **Model** tab on `/tools`. Caveat: uses the
  live prediction row for a finished GW (last hourly compute before it finished), not a
  deadline-locked snapshot — a snapshot table is a follow-up.
- [ ] `docs/plans/2026-08-27-fplguru-master-build-plan.md` — **P4b ✅** row; decrement the count;
  deferred: deadline-locked prediction snapshots, calibration/reliability plot, per-GW trend chart.
- [ ] `docs/RESUME-foundation.md` — top line + a `## P4b` section (task table, the snapshot
  caveat, no migration).
- [ ] Full sweep: `pytest -q -W error`, `ruff check .`, `alembic check`, web `vitest` + `build`.
  Commit `docs: P4b Model Transparency complete`.

---

## Self-Review

**Spec coverage (§5.7):** "last GW xP vs actual" → `last_gw.rows` (Task 2); "rolling MAE/RMSE per
position" → `by_position` + `rolling` from `pointwise_metrics` (Tasks 1,2); "A/B model-version
switch" → both `basic-v1` and `adv-v1` returned side by side and rendered in two columns (Task 3) —
a literal toggle is unnecessary when both are shown at once. Public → no auth (nothing in this app
is authed).

**No migration** — reads `PlayerGwPrediction` / `PlayerGwStat` / `Gameweek` / `Player`. `alembic
check` stays clean. **Caveat documented:** a finished GW's prediction rows are the last hourly
compute, not a deadline snapshot — noted in README + RESUME, snapshot table listed as a follow-up.

**Consistency:** `pointwise_metrics` return shape `{n, mae, rmse, bias}` identical in its tests,
the API `metric_map`, and the web `ModelMetric` type; model-version strings come from
`_MODEL_VERSION` / `_ADV_MODEL_VERSION` (no new literals); `"ALL"` pseudo-position used
consistently.

**Placeholder scan:** Task 2's snippet has intentional cruft (the `names`/`_empty` lines) — the
step text says to clean it; Task 3 is described against the established `ToolsHub` tab pattern.
Task 1 is complete code.

---

## Execution Handoff

Branch `feature/p4b-transparency` off `main`. Subagent-driven, order 1 → 4. Tasks 1 & 2 get a full
review; 3 spec-check + quality-check; 4 spec-check. After Task 4: whole-branch review, PR → `main`,
watch CI, squash-merge.

### Deferred follow-ups
- Deadline-locked `prediction_snapshot` table (worker writes once per GW at deadline) for a
  provably fair backtest-on-live.
- Calibration / reliability plot (predicted-bucket vs realised mean).
- Per-GW MAE/RMSE trend chart (recharts) rather than just overall + rolling.
- Surface the current GW's projection accuracy on the player detail / squad views.
