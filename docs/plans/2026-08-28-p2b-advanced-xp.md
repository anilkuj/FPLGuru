# P2b — Advanced xP Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. TDD; gates `python -m pytest -q -W error` + `python -m ruff check .` + `python -m alembic check` (+ `next build` / `vitest` for the web task).

**Goal:** A non-linear per-position **gradient-boosted regression tree** xP model that uses expected-goals features, produces calibrated floor/ceiling bands from quantile models, and beats the linear `basic-v1` on walk-forward RMSE. Served alongside Basic as `model_version = "adv-v1"`, selectable via `?model=`.

**Architecture:** `fplguru_ml.gbrt` — a **pure-numpy** GBRT (no LightGBM — SAC blocks native `.dll`s, same reason `basic-v1` is hand-rolled ridge). L2 loss for the mean, quantile (pinball) loss for the 0.15 / 0.85 bands. `fplguru_ml.model_advanced.AdvancedXP` bundles one mean GBRT + two quantile GBRTs per position. Trained from the vaastav `merged_gw` CSVs (which already carry `expected_goals` / `expected_assists` / `expected_goals_conceded` / `ict_index`). At serve time the worker builds adv feature rows from the live DB — xG features come from `player_xg` (PitchAPI) when present, else a rolling FPL proxy, else 0. The API resolves `?model=basic|advanced` (default: advanced when adv rows exist). No schema change — reuses `player_gw_predictions` (`xp`, `xp_floor`, `xp_ceiling`, and an approximate `x_*` component split).

**Tech Stack:** numpy (pinned `<2.5`), pandas, FastAPI, Next.js. No new deps, no migration.

---

## Project context (read once)

- Monorepo `D:\AntiGravity\FPLGuru`; branch **`feature/p2b-advanced-xp`** off `main`.
- `packages/ml/src/fplguru_ml/`: `features.py` (`FEATURE_NAMES` [9], `wmean`), `frame.py`
  (`build_training_frame(rows) -> DataFrame` with `FEATURE_NAMES` + `target` + `position` + `gameweek`),
  `ridge.py` (`RidgeModel`), `model_basic.py` (`BasicXP`, `train_basic`, `VERSION="basic-v1"`,
  save/load a dir of `meta.json` + `<POS>.json`), `backtest.py` (`walk_forward(frame) ->
  BacktestResult.metrics_by_position()`), `rollout.py` (`band_halfwidth`, `project_horizon`).
- `packages/ingest/.../historical.py::normalize_merged_gw(csv, season) -> list[dict]` — already emits
  `xg`, `xa` per row (from `expected_goals` / `expected_assists`); **add** `xgc`
  (`expected_goals_conceded`), `ict` (`ict_index`), `goals_conceded`.
- Historical CSVs present: `data/historical/2023-24_merged_gw.csv`, `2024-25_merged_gw.csv`
  (gitignored). Column list confirmed to include `expected_goals`, `expected_assists`,
  `expected_goals_conceded`, `ict_index`, `starts`.
- `scripts/train_xp.py` + `scripts/backtest_xp.py` — Basic pipeline. `packages/ml/artifacts/basic/`
  holds the committed `basic-v1` artifacts (~small JSON).
- Worker `services/worker/src/fplguru_worker/xp.py::compute_and_store_xp(horizon=5)` loads
  `BasicXP.load(_artifact_dir())`, builds per-player feature history from `PlayerGwStat`, upserts
  `PlayerGwPrediction` on `(player_id, gameweek_id, model_version)`. `FPLGURU_XP_ARTIFACT_DIR` env
  overrides the dir. Worker Beat `compute-xp` hourly.
- API `services/api/src/fplguru_api/main.py`: `_MODEL_VERSION = "basic-v1"`; `GET /xp?horizon=`
  (1–5) sums `xp` per player over `horizon_gw <= horizon`; `GET /players/{id}/xp?horizon=` returns
  `per_gw` + `xp_total`. Tests: `client`, `db_session`.
- `PlayerGwPrediction` cols: `player_id, gameweek_id, horizon_gw, model_version, xp, x_minutes,
  x_goals, x_assists, x_cs_or_gc, x_bonus, xp_floor, xp_ceiling`.
- **Baseline:** `python -m pytest -q` → **193 passed**; web `vitest run` → **19 passed**.
- **SAC:** pure Python/numpy only. Do NOT add `lightgbm`, `scikit-learn`, `scipy`.

---

## Task 1: `gbrt.py` — pure-numpy gradient-boosted trees

**Files:** `packages/ml/src/fplguru_ml/gbrt.py`, `packages/ml/tests/test_gbrt.py`.

- [ ] **Step 1: failing test** — `packages/ml/tests/test_gbrt.py`:
```python
import numpy as np

from fplguru_ml.gbrt import GBRT


def _data(n=600, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 3))
    # non-linear target GBRT should fit but ridge can't
    y = (x[:, 0] > 0).astype(float) * 3 + np.sin(x[:, 1]) * 2 + 0.3 * rng.normal(size=n)
    return x, y


def test_gbrt_fits_nonlinear_signal_and_beats_mean():
    x, y = _data()
    m = GBRT.fit(x, y, n_estimators=80, learning_rate=0.1, max_depth=3, seed=1)
    pred = m.predict(x)
    rmse = float(np.sqrt(np.mean((pred - y) ** 2)))
    base = float(np.sqrt(np.mean((y.mean() - y) ** 2)))
    assert rmse < 0.6 * base


def test_gbrt_json_round_trip_is_exact():
    x, y = _data(200)
    m = GBRT.fit(x, y, n_estimators=20, learning_rate=0.2, max_depth=2, seed=2)
    m2 = GBRT.from_json(m.to_json())
    assert np.allclose(m.predict(x), m2.predict(x))


def test_gbrt_quantile_brackets_the_mean():
    x, y = _data(800)
    lo = GBRT.fit(x, y, n_estimators=60, learning_rate=0.1, max_depth=3, seed=3,
                  loss="quantile", alpha=0.15)
    hi = GBRT.fit(x, y, n_estimators=60, learning_rate=0.1, max_depth=3, seed=3,
                  loss="quantile", alpha=0.85)
    plo, phi = lo.predict(x), hi.predict(x)
    # ~70% coverage between the 15th and 85th quantile predictions
    cover = float(np.mean((y >= plo) & (y <= phi)))
    assert 0.55 < cover < 0.9
    assert np.mean(phi - plo) > 0
```

- [ ] **Step 2: implement `packages/ml/src/fplguru_ml/gbrt.py`**
```python
"""Pure-numpy gradient-boosted regression trees (L2 + pinball/quantile loss).
No LightGBM/sklearn — Smart App Control blocks their native binaries, and the
rest of the ML stack is hand-rolled for the same reason."""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

_MAX_BINS = 64  # candidate split thresholds per feature


@dataclass
class _Node:
    feat: int = -1
    thr: float = 0.0
    left: int = -1
    right: int = -1
    value: float = 0.0  # leaf prediction (for the residual target)


def _fit_tree(x, g, max_depth, min_leaf, rng, colsample):
    """Fit one regression tree to gradients `g`. Returns a flat list[_Node]."""
    n, d = x.shape
    nodes: list[_Node] = []

    def build(idx, depth):
        node_i = len(nodes)
        nodes.append(_Node(value=float(g[idx].mean()) if len(idx) else 0.0))
        if depth >= max_depth or len(idx) < 2 * min_leaf:
            return node_i
        feats = (
            rng.choice(d, size=max(1, int(d * colsample)), replace=False)
            if colsample < 1.0
            else range(d)
        )
        best = None  # (gain, feat, thr, left_idx, right_idx)
        parent_sse = float(((g[idx] - g[idx].mean()) ** 2).sum())
        for f in feats:
            col = x[idx, f]
            uniq = np.unique(col)
            if len(uniq) < 2:
                continue
            qs = (
                uniq
                if len(uniq) <= _MAX_BINS
                else np.quantile(col, np.linspace(0.02, 0.98, _MAX_BINS))
            )
            for thr in qs:
                lmask = col <= thr
                if lmask.sum() < min_leaf or (~lmask).sum() < min_leaf:
                    continue
                gl, gr = g[idx][lmask], g[idx][~lmask]
                sse = ((gl - gl.mean()) ** 2).sum() + ((gr - gr.mean()) ** 2).sum()
                gain = parent_sse - sse
                if best is None or gain > best[0]:
                    best = (gain, int(f), float(thr), idx[lmask], idx[~lmask])
        if best is None or best[0] <= 1e-9:
            return node_i
        _, f, thr, li, ri = best
        nodes[node_i].feat = f
        nodes[node_i].thr = thr
        nodes[node_i].left = build(li, depth + 1)
        nodes[node_i].right = build(ri, depth + 1)
        return node_i

    build(np.arange(n), 0)
    return nodes


def _predict_tree(nodes, x):
    out = np.empty(len(x))
    for i, row in enumerate(x):
        j = 0
        while nodes[j].feat >= 0:
            j = nodes[j].left if row[nodes[j].feat] <= nodes[j].thr else nodes[j].right
        out[i] = nodes[j].value
    return out


class GBRT:
    def __init__(self, base, trees, lr, loss, alpha):
        self.base = float(base)
        self.trees = trees  # list[list[_Node]]
        self.lr = float(lr)
        self.loss = loss
        self.alpha = float(alpha)

    @classmethod
    def fit(cls, x, y, *, n_estimators=200, learning_rate=0.05, max_depth=3,
            min_leaf=20, subsample=0.8, colsample=1.0, loss="l2", alpha=0.5,
            seed=0):
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        rng = np.random.default_rng(seed)
        base = float(np.quantile(y, alpha) if loss == "quantile" else y.mean())
        f = np.full(len(y), base)
        trees = []
        for _ in range(n_estimators):
            if loss == "quantile":
                grad = np.where(y >= f, alpha, alpha - 1.0)
            else:
                grad = y - f
            if subsample < 1.0:
                sub = rng.choice(len(y), size=int(len(y) * subsample), replace=False)
            else:
                sub = np.arange(len(y))
            tree = _fit_tree(x[sub], grad[sub], max_depth, min_leaf, rng, colsample)
            f = f + learning_rate * _predict_tree(tree, x)
            trees.append(tree)
        return cls(base, trees, learning_rate, loss, alpha)

    def predict(self, x):
        x = np.asarray(x, float)
        out = np.full(len(x), self.base)
        for tree in self.trees:
            out = out + self.lr * _predict_tree(tree, x)
        return out

    def to_json(self) -> str:
        return json.dumps({
            "base": self.base, "lr": self.lr, "loss": self.loss, "alpha": self.alpha,
            "trees": [
                [[n.feat, n.thr, n.left, n.right, n.value] for n in tree]
                for tree in self.trees
            ],
        })

    @classmethod
    def from_json(cls, s: str) -> "GBRT":
        d = json.loads(s)
        trees = [
            [_Node(int(a), float(b), int(c), int(e), float(v)) for a, b, c, e, v in tree]
            for tree in d["trees"]
        ]
        return cls(d["base"], trees, d["lr"], d["loss"], d["alpha"])
```

- [ ] **Step 3:** `python -m pytest packages/ml/tests/test_gbrt.py -q` → **3 passed**.
  `python -m pytest -q -W error` → **196 passed**. `ruff` clean.
  Commit `feat(ml): pure-numpy gradient-boosted regression trees (L2 + quantile)`.

---

## Task 2: advanced features

**Files:** `packages/ingest/src/fplguru_ingest/historical.py`, `packages/ingest/tests/test_fpl_normalizers.py` (or the historical test), `packages/ml/src/fplguru_ml/features.py`, `packages/ml/src/fplguru_ml/frame.py`, `packages/ml/tests/test_frame.py` (extend).

- [ ] **Step 1: `normalize_merged_gw`** — add to each row dict:
  `"xgc": float(r.expected_goals_conceded)`, `"ict": float(r.ict_index)`,
  `"goals_conceded": int(r.goals_conceded)`. Update the historical-normalizer test to assert the
  three new keys on `rows[0]`.

- [ ] **Step 2: `features.py`** — add:
```python
FEATURE_NAMES_ADV = FEATURE_NAMES + [
    "form_xg_5", "form_xa_5", "xg_overperf_5", "form_xgc_5", "form_ict_5",
]
```
(`xg_overperf_5` = recent mean of `goals - xg` — a finishing-luck / regression signal.)

- [ ] **Step 3: `frame.py`** — a new `build_adv_frame(rows) -> DataFrame` that reuses the Basic
  per-player loop but, per kept row, also computes over the prior appearances:
  `form_xg_5 = mean(xg[-5:])`, `form_xa_5 = mean(xa[-5:])`,
  `xg_overperf_5 = mean((g - xg)[-5:])`, `form_xgc_5 = mean(xgc[-5:])`,
  `form_ict_5 = mean(ict[-5:])` (0.0 when the field is missing/NaN). Output columns =
  `FEATURE_NAMES_ADV` + `target` + `position` + `gameweek`. Keep `build_training_frame` untouched.
  (Simplest: factor the shared prior-appearance bookkeeping into a helper both frames call, or
  copy the loop — DRY is nice but a second ~40-line function is acceptable here.)

- [ ] **Step 4: `test_frame.py`** — a small synthetic `rows` list (2 seasons, a couple players,
  `xg`/`xa`/`xgc`/`ict` present) asserting `build_adv_frame` returns the `FEATURE_NAMES_ADV`
  columns and that `xg_overperf_5` is `mean(goals - xg)` for a hand-checked row.

- [ ] **Step 5:** `python -m pytest packages/ml packages/ingest -q` → pass.
  `python -m pytest -q -W error` → **~198 passed**. `ruff` clean.
  Commit `feat(ml): advanced xG feature set + build_adv_frame`.

---

## Task 3: `model_advanced.py`

**Files:** `packages/ml/src/fplguru_ml/model_advanced.py`, `packages/ml/tests/test_model_advanced.py`.

- [ ] **Step 1: failing test** — train `AdvancedXP` on a small synthetic adv frame; assert
  `.positions()`, `.predict_rows(pos, rows)` returns floats, `.predict_bands(pos, rows)` returns
  `(lo, hi)` with `lo <= mid <= hi` elementwise (allow a small epsilon), save→load round-trips
  predictions, `.baseline(pos)` returns the position mean, `.version == "adv-v1"`.

- [ ] **Step 2: implement**
```python
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fplguru_ml.features import FEATURE_NAMES_ADV
from fplguru_ml.gbrt import GBRT

VERSION = "adv-v1"
_LO, _HI = 0.15, 0.85


class AdvancedXP:
    def __init__(self, mean_models, lo_models, hi_models, global_mean,
                 pos_means, version=VERSION):
        self._mean = mean_models
        self._lo = lo_models
        self._hi = hi_models
        self._global_mean = float(global_mean)
        self._pos_means = dict(pos_means or {})
        self.version = version
        self.feature_names = list(FEATURE_NAMES_ADV)

    def positions(self):
        return sorted(self._mean)

    def baseline(self, position):
        return float(self._pos_means.get(position, self._global_mean))

    def _x(self, rows):
        return np.array([[float(r[k]) for k in self.feature_names] for r in rows], float)

    def predict_rows(self, position, rows):
        if not rows:
            return []
        m = self._mean.get(position)
        if m is None:
            return [self.baseline(position)] * len(rows)
        return [float(v) for v in m.predict(self._x(rows))]

    def predict_bands(self, position, rows):
        if not rows:
            return [], []
        lo, hi = self._lo.get(position), self._hi.get(position)
        if lo is None or hi is None:
            mid = np.array(self.predict_rows(position, rows))
            return list(mid - 2.0), list(mid + 2.0)
        x = self._x(rows)
        return [float(v) for v in lo.predict(x)], [float(v) for v in hi.predict(x)]

    def save(self, directory):
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({
            "version": self.version, "global_mean": self._global_mean,
            "feature_names": self.feature_names, "positions": self.positions(),
            "pos_means": self._pos_means,
        }))
        for pos in self.positions():
            (d / f"{pos}.mean.json").write_text(self._mean[pos].to_json())
            (d / f"{pos}.lo.json").write_text(self._lo[pos].to_json())
            (d / f"{pos}.hi.json").write_text(self._hi[pos].to_json())

    @classmethod
    def load(cls, directory):
        d = Path(directory)
        meta = json.loads((d / "meta.json").read_text())
        p = meta["positions"]
        rd = lambda pos, k: GBRT.from_json((d / f"{pos}.{k}.json").read_text())  # noqa: E731
        return cls({x: rd(x, "mean") for x in p}, {x: rd(x, "lo") for x in p},
                   {x: rd(x, "hi") for x in p}, meta["global_mean"],
                   meta.get("pos_means", {}))


def train_advanced(frame: pd.DataFrame, **gbrt_kw) -> AdvancedXP:
    kw = dict(n_estimators=250, learning_rate=0.05, max_depth=3, min_leaf=25,
              subsample=0.8, seed=0)
    kw.update(gbrt_kw)
    if frame.empty:
        return AdvancedXP({}, {}, {}, 0.0, {})
    mean_m, lo_m, hi_m = {}, {}, {}
    for pos, g in frame.groupby("position"):
        if len(g) < 200:
            continue
        x = g[FEATURE_NAMES_ADV].to_numpy(float)
        y = g["target"].to_numpy(float)
        mean_m[pos] = GBRT.fit(x, y, loss="l2", **kw)
        lo_m[pos] = GBRT.fit(x, y, loss="quantile", alpha=_LO, **kw)
        hi_m[pos] = GBRT.fit(x, y, loss="quantile", alpha=_HI, **kw)
    pos_means = {str(k): float(v) for k, v in frame.groupby("position")["target"].mean().items()}
    return AdvancedXP(mean_m, lo_m, hi_m, float(frame["target"].mean()), pos_means)
```

- [ ] **Step 3:** `python -m pytest packages/ml -q` → pass. Full suite → **~200 passed**.
  Commit `feat(ml): AdvancedXP — per-position GBRT bundle with quantile bands`.

---

## Task 4: backtest + real artifacts

**Files:** `packages/ml/src/fplguru_ml/backtest.py` (add `walk_forward_adv`), `scripts/train_adv_xp.py`, `scripts/backtest_adv_xp.py`, `packages/ml/tests/test_backtest.py` (extend).

- [ ] **Step 1:** `walk_forward_adv(frame, *, min_train_gw=5, **gbrt_kw) -> BacktestResult` —
  mirror `walk_forward` but `train_advanced` on `frame[gameweek < test_gw]` and predict the test GW;
  `baseline` column = the per-position train mean (so `metrics_by_position()` yields
  `rmse` vs `baseline_rmse`). Keep `n_estimators` low in the default so the test is fast
  (`n_estimators=60`), scripts override to 250.

- [ ] **Step 2: `scripts/train_adv_xp.py`** — like `train_xp.py` but
  `build_adv_frame` + `train_advanced` + `model.save("packages/ml/artifacts/advanced")`.
  `scripts/backtest_adv_xp.py` — like `backtest_xp.py` but `walk_forward_adv`, and also load the
  Basic frame + `walk_forward` so the report has an **adv vs basic** RMSE table per position; write
  `docs/xp-backtest/adv-<date>.md`.

- [ ] **Step 3: run for real:**
  ```
  python scripts/train_adv_xp.py --csv data/historical/2023-24_merged_gw.csv data/historical/2024-25_merged_gw.csv --out packages/ml/artifacts/advanced
  python scripts/backtest_adv_xp.py --csv data/historical/2024-25_merged_gw.csv
  ```
  Commit the `packages/ml/artifacts/advanced/*.json` (they'll be larger than Basic — a few hundred
  KB total; if any single file > ~1 MB, drop `n_estimators` to 150). Commit the backtest report.
  **Acceptance:** adv-v1 RMSE ≤ basic-v1 RMSE for **≥ 3 of 4** position groups (M3 criterion). If
  not met, tune (`max_depth` 4, `learning_rate` 0.03, more trees) and re-run; record the final
  numbers in the report and in this plan's Self-Review.

- [ ] **Step 4:** targeted tests green; full suite; `ruff`.
  Commit `feat(ml): advanced walk-forward backtest + trained adv-v1 artifacts`.

---

## Task 5: serve advanced predictions

**Files:** `services/worker/src/fplguru_worker/xp.py`, `services/worker/tests/test_compute_xp.py` (extend), `packages/core/src/fplguru_core/settings.py` (add `adv_xp_artifact_dir: str = "packages/ml/artifacts/advanced"`).

- [ ] **Step 1:** factor the per-player prior-appearance history builder so it can also emit the
  adv fields. For each future GW feature row add `form_xg_5` / `form_xa_5` / `xg_overperf_5` /
  `form_xgc_5` / `form_ict_5`:
  - if the player has `player_xg` rows joined via `Fixture` (PitchAPI data present): rolling means
    of `xg` / `xag` and `goals - xg` over the last 5;
  - else if `player_gw_stats` has usable proxies: 0.0 for xG/xa (FPL live stats don't carry xG),
    `form_ict_5` from... not available either → 0.0;
  - else 0.0.
  (In practice, with no PitchAPI key configured, these are 0.0 and the GBRT leans on the shared
  Basic features — that's fine and documented.)

- [ ] **Step 2:** if `AdvancedXP.load(adv_dir)` succeeds and has models, ALSO compute + upsert
  `adv-v1` predictions per player-GW: `xp` from `predict_rows`, `xp_floor`/`xp_ceiling` from
  `predict_bands` (clip floor at 0), and an **approximate component split**:
  `x_minutes ≈ starts_rate_5 * 90`; `attack = max(xp - 2.0, 0)` split into `x_goals` / `x_assists`
  by the player's recent goal:assist ratio (default 0.6 / 0.4); `x_cs_or_gc` a small
  position-based constant scaled by `form_xgc_5`; `x_bonus ≈ 0.15 * xp`. Mark approximate in a
  code comment. Keep the Basic path unchanged. One `_record(session, "xp_compute", "ok", …)` covering both.

- [ ] **Step 3:** extend `test_compute_xp.py` — seed a player with enough `PlayerGwStat` history +
  place `AdvancedXP` artifacts under a tmp dir via `FPLGURU_ADV_XP_ARTIFACT_DIR`, run
  `compute_and_store_xp`, assert both `basic-v1` and `adv-v1` rows exist for the player and the
  `adv-v1` rows have `xp_ceiling > xp > xp_floor >= 0`.

- [ ] **Step 4:** full suite → green. `ruff`, `alembic check`.
  Commit `feat(worker): compute + store adv-v1 predictions with quantile bands`.

---

## Task 6: API `?model=` + resolver

**Files:** `services/api/src/fplguru_api/main.py`, `services/api/tests/test_xp_api.py` (extend, or `test_advanced_xp_api.py`).

- [ ] **Step 1:** replace the bare `_MODEL_VERSION` use in `/xp` and `/players/{id}/xp` with a
  resolver: `?model=basic|advanced|auto` (default `auto`). `auto` → `"adv-v1"` if any
  `PlayerGwPrediction.model_version == "adv-v1"` row exists, else `"basic-v1"`. Add the resolved
  `model` string to both responses. `/players/{id}/xp` `per_gw` already returns `xp_floor` /
  `xp_ceiling` — confirm they're included; if not, add them.
- [ ] **Step 2:** tests — seed both `basic-v1` and `adv-v1` rows; `GET /xp` (auto) → adv;
  `GET /xp?model=basic` → basic numbers; `GET /players/{id}/xp` includes `floor`/`ceiling` and
  `model: "adv-v1"`.
- [ ] **Step 3:** full suite → green. Commit `feat(api): xp model selector (basic|advanced|auto)`.

---

## Task 7: web — model toggle + bands

**Files:** `apps/web/src/lib/api.ts` (getXp / getPlayerXp gain a `model` arg + `XpRow` gains
`floor`/`ceiling`/`model`), `apps/web/src/lib/api.*.test.ts` (extend one), `apps/web/src/app/squad/SquadTable.tsx`
(+ maybe a small xP detail), `apps/web/src/components/` a `ModelBadge`.

- [ ] Squad table: an "advanced" / "basic" segmented `Button` pair (persist via `prefs`), and the
  xP column shows `xp` with a muted `floor–ceiling` under it when present. A small badge showing
  which model is live.
- [ ] `vitest run` → 20 passed. `next build` → success.
  Commit `feat(web): xP model toggle + floor/ceiling`.

---

## Task 8: docs

- [ ] `README.md` — the xP section: note the Advanced (GBRT) tier, xG features, quantile bands,
  `?model=`, and that adv features are 0 until a PitchAPI key populates `player_xg`. Link the new
  backtest report.
- [ ] `docs/plans/2026-08-27-fplguru-master-build-plan.md` — **P2b ✅**; record the adv-vs-basic
  RMSE result; note **P2c (LLM explanation) is now unblocked**. Decrement the count.
- [ ] `docs/RESUME-foundation.md` — top line + a `## P2b` section (task table, the RMSE numbers,
  the "adv features are 0 without PitchAPI" caveat, artifact size).
- [ ] Full verification: `pytest -q -W error`, `ruff`, `alembic check`, web `vitest` + `build`.
  Commit `docs: P2b Advanced xP complete`.

---

## Self-Review

**Spec coverage (master §3 P2b / §5.2 Advanced):** non-linear per-position model → GBRT (Task 1,3);
xG features → `FEATURE_NAMES_ADV` from `player_xg` / historical CSV (Task 2); quantile floor/ceiling
bands → quantile GBRTs (Task 1,3,5); iterative multi-GW rollout → reuses the existing per-GW
feature-row approach (each future GW predicted from its own row) — full compounding-rotation rollout
is a follow-up; isotonic calibration + SHAP → **deferred** (SHAP needs a tree-path attribution pass;
the approximate `x_*` split + P4b transparency page cover the user-facing need for now). LightGBM →
replaced by a pure-numpy GBRT for SAC. **Ensemble** → single GBRT per position (bagging via
`subsample` only) — a true multi-seed ensemble is a cheap follow-up.

**No migration** — `player_gw_predictions` already has every column. `alembic check` must stay clean.

**Consistency:** `GBRT.fit(...).to_json()/from_json()` round-trips (Task 1 test); `AdvancedXP` save
layout `<POS>.{mean,lo,hi}.json` + `meta.json` mirrors `BasicXP`; `FEATURE_NAMES_ADV` used
identically in `build_adv_frame`, `train_advanced`, and the worker feature-row builder;
`model_version` string `"adv-v1"` consistent across `model_advanced.VERSION`, worker, API resolver,
and the backtest report.

**Placeholder scan:** Tasks 5 & 7 give intent + the component-split formula rather than full code —
acceptable (worker follows the existing `compute_and_store_xp` structure; the web toggle is
presentational). All ML core (Tasks 1–3) is complete code.

---

## Execution Handoff

Branch `feature/p2b-advanced-xp` off `main`. Subagent-driven, order 1 → 8. Tasks 1–3 (the model) +
Task 5 (serving) get a full review; Tasks 2, 4, 6 spec-check + quality-check; Tasks 7, 8 spec-check.
Task 4 runs real training — commit the artifacts + report. After Task 8: whole-branch review, PR →
`main`, watch CI, squash-merge. **Then P2c (LLM explanation layer) is unblocked.**

### Deferred follow-ups
- Full compounding multi-GW rollout (rotation risk, fixture swings) feeding the GBRT.
- True SHAP / tree-path feature attribution → feeds P2c and P4b.
- Isotonic calibration of the mean predictions.
- Multi-seed GBRT ensemble (average 3–5 seeds).
- Real component models (`x_goals` etc.) instead of the heuristic split.
- Retrain `sync` job + artifact versioning in the DB.
