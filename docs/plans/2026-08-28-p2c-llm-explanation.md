# P2c — LLM Explanation Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. TDD; gates `python -m pytest -q -W error` + `python -m ruff check .` + `python -m alembic check` (+ `vitest` / `next build` for the web task).

**Goal:** An on-demand, cached, plain-English rationale for a player's **Advanced (`adv-v1`) xP** projection — what's driving it up or down — served from `GET /players/{id}/xp/explain`, with a template fallback when the LLM is unconfigured / over budget.

**Architecture:** The Advanced GBRT has no cheap exact SHAP, so `AdvancedXP.explain_row` computes a **local occlusion attribution**: for each feature, swap in that position's training-set median and measure the change in the mean prediction; the largest signed changes are the "drivers". Medians are stored in the adv `meta.json` (one retrain). A new pure package `fplguru-explain` turns `(player, next fixtures, drivers, xp, band)` into a Gemini prompt and a template string. The API endpoint rebuilds the player's served feature row (shared `fplguru_ml.serving` helper, also used by the worker), runs `predict_rows` / `predict_bands` / `explain_row`, then calls `generate_within_budget` (from P2e) and caches the text in a new `xp_rationale` table (mirrors `captain_rationale`). The web squad view gets a per-row "Why?" expander.

**Tech Stack:** numpy, FastAPI, SQLAlchemy/Alembic, httpx (Gemini, via `fplguru-llm`), Next.js. One migration (`0012`, one `create_table`). No new runtime deps.

---

## Project context (read once)

- Branch **`feature/p2c-llm-explanation`** off `main` (P2b merged at `eb29b8a`).
- **`fplguru_ml.model_advanced`** — `AdvancedXP` bundle: `._mean/._lo/._hi` dicts of `GBRT` per
  position, `predict_rows(pos, rows)`, `predict_bands(pos, rows) -> (floor, ceiling)`,
  `baseline(pos)`, `feature_names` (= `FEATURE_NAMES_ADV`, 14), `save(dir)` / `load(dir)` with
  `meta.json` (`version`, `global_mean`, `feature_names`, `positions`, `pos_means`) +
  `<POS>.{mean,lo,hi}.json`. `train_advanced(frame, *, min_rows=200, **gbrt_kw)`.
- **`fplguru_ml.features`** — `FEATURE_NAMES` (9), `ADV_EXTRA_FEATURES` (5:
  `form_xg_5 form_xa_5 xg_overperf_5 form_xgc_5 form_ict_5`), `FEATURE_NAMES_ADV`,
  `feature_row_from_history(history, *, was_home, value, opp_conceded_to_pos_5) -> dict | None`
  (needs ≥3 appearances; `history` = prior appearances oldest-first, dicts with
  `total_points/minutes/goals/assists`).
- **`fplguru_ml.gbrt.GBRT`** — `.predict(X) -> np.ndarray`, `.base`, `.trees`, `.lr`.
- **`packages/ml/artifacts/advanced/`** — committed `adv-v1` artifacts (~660 KB).
  `scripts/train_adv_xp.py --csv data/historical/*_merged_gw.csv --out packages/ml/artifacts/advanced`.
- **Worker** `services/worker/src/fplguru_worker/xp.py::compute_and_store_xp` — has
  `_feature_plan(p, h, side, conceded, future_gws) -> (triples, fallbacks)` where
  `triples = [(horizon_gw, gameweek_id, basic_feature_row)]`, `_adv_feature_row(fr)` (basic row +
  5 zero xG feats), `_component_split(pos, fr, xp)`, `_load_adv()`, `_adv_artifact_dir()`
  (`FPLGURU_ADV_XP_ARTIFACT_DIR` → `settings.adv_xp_artifact_dir`).
- **`services/api/src/fplguru_api/llm.py`** — `generate_within_budget(db, feature, prompt, *,
  max_output_tokens=200) -> str | None` (None ⇒ unconfigured / over `llm_monthly_usd_cap` / error;
  logs an `LlmCall` row either way).
- **`services/api/src/fplguru_api/main.py`** — `_resolve_model_version(db, model="auto") -> str`
  (`auto|basic|advanced`); `GET /players/{id}/xp?horizon=&model=` returns `per_gw` with
  `floor`/`ceiling`/`x_*`; `_MODEL_VERSION="basic-v1"`, `_ADV_MODEL_VERSION="adv-v1"`.
  Captain precedent: `_template_rationale`, `_rationale_for` (cache-check → `generate_within_budget`
  → cache `CaptainRationale` → else template), `rationale_prompt` from `fplguru_captain`.
- **`CaptainRationale`** model (`packages/core/src/fplguru_core/models.py:330`) — copy its shape.
- **Alembic head `0011`** (plain string revisions). `packages/core/tests/test_models.py::
  test_expected_tables_registered` asserts the **exact** table-name set — must add `xp_rationale`.
  JSON `server_default` breaks `alembic check`; a nullable column with a Python-side default is fine.
- **Root `pyproject.toml`** `[tool.ruff.lint.isort] known-first-party` list — add `fplguru_explain`.
  `requirements-dev.txt` — add `-e ./packages/explain`.
- **Baseline:** `pytest -q` → **209 passed**; web `vitest run` → **20 passed**.
- **SAC:** pure Python/numpy only.

---

## Task 1: `AdvancedXP.explain_row` + feature medians

**Files:** `packages/ml/src/fplguru_ml/model_advanced.py`, `packages/ml/tests/test_model_advanced.py` (extend).

- [ ] **Step 1 — failing test** (`test_model_advanced.py`):
```python
def test_explain_row_ranks_drivers_by_prediction_delta():
    frame = _frame()
    model = train_advanced(frame, min_rows=50, n_estimators=40, seed=1)
    row = frame[frame.position == "MID"][FEATURE_NAMES_ADV].to_dict("records")[0]
    drivers = model.explain_row("MID", row, top=3)
    assert len(drivers) == 3
    # each is (feature_name, signed_delta) with feature in the adv set
    for name, delta in drivers:
        assert name in FEATURE_NAMES_ADV
        assert isinstance(delta, float)
    # sorted by descending |delta|
    mags = [abs(d) for _, d in drivers]
    assert mags == sorted(mags, reverse=True)


def test_feature_medians_persist(tmp_path):
    frame = _frame()
    model = train_advanced(frame, min_rows=50, n_estimators=20, seed=2)
    model.save(tmp_path / "adv")
    reloaded = AdvancedXP.load(tmp_path / "adv")
    assert set(reloaded.feature_medians()) == set(model.positions())
    assert len(reloaded.feature_medians()["MID"]) == len(FEATURE_NAMES_ADV)
```

- [ ] **Step 2 — implement:**
  - `train_advanced`: after fitting, compute
    `medians = {pos: g[FEATURE_NAMES_ADV].median().tolist() for pos, g in frame.groupby("position") if len(g) >= min_rows}`
    and pass to `AdvancedXP(... , feature_medians=medians)`.
  - `AdvancedXP.__init__(..., feature_medians: dict[str, list[float]] | None = None)` →
    `self._medians = {k: [float(x) for x in v] for k, v in (feature_medians or {}).items()}`.
  - `feature_medians(self) -> dict[str, list[float]]: return dict(self._medians)`.
  - `save`: add `"feature_medians": self._medians` to `meta.json`.
  - `load`: pass `meta.get("feature_medians", {})`.
  - `explain_row(self, position, row, *, top=3) -> list[tuple[str, float]]`:
    ```python
    m = self._mean.get(position)
    if m is None:
        return []
    base = [float(row[k]) for k in self.feature_names]
    meds = self._medians.get(position) or base
    p0 = float(m.predict([base])[0])
    out = []
    for i, name in enumerate(self.feature_names):
        if abs(base[i] - meds[i]) < 1e-12:
            continue
        swapped = list(base); swapped[i] = meds[i]
        delta = p0 - float(m.predict([swapped])[0])   # +ve => this feature pushed xP up
        out.append((name, round(delta, 4)))
    out.sort(key=lambda t: abs(t[1]), reverse=True)
    return out[:top]
    ```

- [ ] **Step 3:** `pytest packages/ml -q` green. **Retrain** so the committed artifact gains medians:
  `python scripts/train_adv_xp.py --csv data/historical/2023-24_merged_gw.csv data/historical/2024-25_merged_gw.csv --out packages/ml/artifacts/advanced --n-estimators 90 --learning-rate 0.07 --max-depth 3`
  — commit the updated `packages/ml/artifacts/advanced/meta.json` (tree files may be byte-identical; commit whatever changed). Verify `test_xp_api.py::test_model_version_matches_trained_artifact` still passes.
  Commit `feat(ml): AdvancedXP.explain_row occlusion attribution + feature medians`.

---

## Task 2: `fplguru-explain` package (pure prompt + template)

**Files:** create `packages/explain/pyproject.toml`, `packages/explain/src/fplguru_explain/__init__.py`,
`packages/explain/tests/test_explain.py`; edit root `pyproject.toml` (known-first-party),
`requirements-dev.txt`.

- [ ] **Step 1 — `pyproject.toml`** (copy `packages/captain/pyproject.toml`, s/captain/explain/,
  deps: none beyond python).

- [ ] **Step 2 — failing test** (`test_explain.py`):
```python
from fplguru_explain import DRIVER_PHRASES, explanation_prompt, template_explanation

PLAYER = {"web_name": "Saka", "position": "MID", "team_short": "ARS"}
FIX = [{"opponent_short": "LUT", "was_home": True, "difficulty": 2},
       {"opponent_short": "CHE", "was_home": False, "difficulty": 4}]
DRIVERS = [("form_xg_5", 0.9), ("opp_conceded_to_pos_5", 0.4), ("starts_rate_5", -0.3)]


def test_template_is_deterministic_and_mentions_player_and_xp():
    t = template_explanation(PLAYER, xp=6.4, floor=3.1, ceiling=9.0, drivers=DRIVERS, horizon=2)
    assert "Saka" in t and "6.4" in t
    assert DRIVER_PHRASES["form_xg_5"] in t          # "recent xG"
    assert t == template_explanation(PLAYER, xp=6.4, floor=3.1, ceiling=9.0,
                                     drivers=DRIVERS, horizon=2)


def test_prompt_lists_drivers_with_direction_and_forbids_preamble():
    p = explanation_prompt(PLAYER, FIX, DRIVERS, xp=6.4, floor=3.1, ceiling=9.0, horizon=2)
    assert "Saka" in p and "6.4" in p
    assert "raises" in p.lower() and "lowers" in p.lower()   # direction words present
    assert "no preamble" in p.lower()
```

- [ ] **Step 3 — implement `__init__.py`:**
```python
"""Pure helpers: turn Advanced-xP drivers into an LLM prompt or a template string."""
from __future__ import annotations

from typing import Any

__all__ = ["DRIVER_PHRASES", "explanation_prompt", "template_explanation"]

DRIVER_PHRASES = {
    "form_points_3": "very recent scoring", "form_points_5": "recent scoring",
    "form_minutes_3": "recent minutes", "starts_rate_5": "starts security",
    "form_goals_5": "recent goals", "form_assists_5": "recent assists",
    "was_home": "home advantage", "value": "price bracket",
    "opp_conceded_to_pos_5": "how much upcoming opponents concede to this position",
    "form_xg_5": "recent xG", "form_xa_5": "recent xA",
    "xg_overperf_5": "finishing vs xG", "form_xgc_5": "defensive workload (xGC)",
    "form_ict_5": "overall involvement (ICT)",
}


def _phrase(name: str) -> str:
    return DRIVER_PHRASES.get(name, name.replace("_", " "))


def _driver_lines(drivers: list[tuple[str, float]]) -> str:
    return "; ".join(
        f"{_phrase(n)} {'raises' if d >= 0 else 'lowers'} the projection"
        for n, d in drivers
    ) or "no single dominant factor"


def template_explanation(player: dict[str, Any], *, xp: float, floor: float,
                         ceiling: float, drivers: list[tuple[str, float]],
                         horizon: int) -> str:
    return (
        f"{player['web_name']} ({player['team_short']}, {player['position']}) projects "
        f"{xp:.1f} pts over the next {horizon} GW(s) (range {floor:.1f}-{ceiling:.1f}). "
        f"Main factors: {_driver_lines(drivers)}."
    )


def explanation_prompt(player: dict[str, Any], fixtures: list[dict[str, Any]],
                       drivers: list[tuple[str, float]], *, xp: float, floor: float,
                       ceiling: float, horizon: int) -> str:
    fx = ", ".join(
        f"{f['opponent_short']} ({'H' if f['was_home'] else 'A'}, FDR {f['difficulty']})"
        for f in fixtures[:horizon]
    ) or "unknown"
    dl = "; ".join(
        f"{_phrase(n)} ({'+' if d >= 0 else '-'})" for n, d in drivers
    ) or "none"
    return (
        f"You are an FPL analyst. In ONE or TWO plain sentences, explain the projected points for "
        f"{player['web_name']} ({player['team_short']}, {player['position']}): {xp:.1f} pts over "
        f"the next {horizon} gameweek(s), likely range {floor:.1f}-{ceiling:.1f}. "
        f"Upcoming fixtures: {fx}. The model says these factors move it "
        f"(+ raises, - lowers): {dl}. No preamble, no bullet points, no numbers list."
    )
```

- [ ] **Step 4:** add `fplguru_explain` to `known-first-party`; add `-e ./packages/explain` to
  `requirements-dev.txt`; `pip install -e ./packages/explain`. `pytest packages/explain -q` green,
  `ruff` clean. Commit `feat(explain): fplguru-explain prompt + template helpers`.

---

## Task 3: `xp_rationale` table (`0012`)

**Files:** `packages/core/src/fplguru_core/models.py`, `alembic/versions/0012_xp_rationale.py`,
`packages/core/tests/test_models.py` (update the exact-set assertion).

- [ ] **Step 1 — model** (after `CaptainRationale`):
```python
class XpRationale(_TimestampMixin, Base):
    """Cached LLM explanation of a player's Advanced-xP projection for a gameweek."""
    __tablename__ = "xp_rationale"
    __table_args__ = (
        UniqueConstraint("player_id", "gameweek_id", "model_version",
                         name="uq_xp_rationale_player_id_gameweek_id_model_version"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    model_version: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String(48), default="")
```

- [ ] **Step 2 — migration `0012_xp_rationale.py`** (`revision='0012'`, `down_revision='0011'`),
  one `op.create_table('xp_rationale', ...)` with the two FKs (`op.f(...)` names), PK `pk_xp_rationale`,
  `UniqueConstraint('player_id','gameweek_id','model_version', name='uq_xp_rationale_player_id_gameweek_id_model_version')`,
  `created_at`/`updated_at` `server_default=sa.text('now()')`, and the two `ix_` indexes; matching
  `downgrade()`.

- [ ] **Step 3:** add `"xp_rationale"` to `test_expected_tables_registered`.
  `python -m alembic upgrade head` then `python -m alembic check` → "No new upgrade operations".
  `pytest packages/core -q` green. Commit `feat(core): xp_rationale cache table (0012)`.

---

## Task 4: `GET /players/{id}/xp/explain`

**Files:** `packages/ml/src/fplguru_ml/serving.py` (new, tiny), `packages/ml/tests/test_serving.py`,
`services/worker/src/fplguru_worker/xp.py` (use the shared helper — no behaviour change),
`services/api/src/fplguru_api/main.py`, `services/api/tests/test_xp_explain_api.py`.

- [ ] **Step 1 — `fplguru_ml/serving.py`:**
```python
"""Shared serving-time feature-row assembly for the xP models."""
from __future__ import annotations

from fplguru_ml.features import ADV_EXTRA_FEATURES, feature_row_from_history


def adv_feature_row(history, *, was_home, value, opp_conceded_to_pos_5):
    """Advanced (14-feature) row, or None if history is too thin. The 5 xG
    features are 0.0 until player_xg carries an FPL id mapping."""
    fr = feature_row_from_history(
        history, was_home=was_home, value=value,
        opp_conceded_to_pos_5=opp_conceded_to_pos_5,
    )
    if fr is None:
        return None
    return {**fr, **{k: 0.0 for k in ADV_EXTRA_FEATURES}}
```
  `test_serving.py`: thin history → None; ≥3 appearances → dict with all 14 `FEATURE_NAMES_ADV`
  keys, xG feats 0.0.
  Then in `xp.py` replace the local `_adv_feature_row` body with
  `from fplguru_ml.serving import adv_feature_row` and `_adv_feature_row = adv_feature_row` (or call
  it directly). Run `pytest services/worker -q` — unchanged (29 passed).

- [ ] **Step 2 — failing API test** (`test_xp_explain_api.py`): seed team, gameweeks (one finished
  ×4 with `PlayerGwStat` history for player 11, one `is_next`), a `Fixture` for the next GW, and
  `adv-v1` `PlayerGwPrediction` rows. Point `FPLGURU_ADV_XP_ARTIFACT_DIR` at a tmp dir holding a
  real small `AdvancedXP` (`train_advanced` on a tiny synthetic adv frame, saved). Assert:
  - `GET /players/11/xp/explain?horizon=2` → 200, body has `player_id`, `model == "adv-v1"`,
    `xp_total`, `floor`, `ceiling`, `drivers` (list of `{feature, phrase, direction}`), `text`
    (non-empty), `source in {"llm","template"}` (no key in tests ⇒ `"template"`).
  - second call returns the **same** `text` and does not add an `LlmCall` beyond the first
    (cache hit — actually template path doesn't cache; see Step 3).
  - `GET /players/999/xp/explain` → 404.

- [ ] **Step 3 — implement** in `main.py`:
```python
@app.get("/players/{player_id}/xp/explain")
async def player_xp_explain(player_id: int, horizon: int = Query(3, ge=1, le=5),
                            model: str = Query("advanced", pattern="^(auto|basic|advanced)$"),
                            db: AsyncSession = Depends(get_db)) -> dict:
    mv = await _resolve_model_version(db, model)
    player = (await db.execute(select(Player).where(Player.id == player_id))).scalar_one_or_none()
    if player is None:
        raise HTTPException(404, "unknown player")
    preds = (await db.execute(
        select(PlayerGwPrediction).where(
            PlayerGwPrediction.player_id == player_id,
            PlayerGwPrediction.model_version == mv,
            PlayerGwPrediction.horizon_gw <= horizon,
        ).order_by(PlayerGwPrediction.horizon_gw)
    )).scalars().all()
    if not preds:
        raise HTTPException(404, "no predictions for player")
    gw_id = preds[0].gameweek_id
    xp_total = float(sum(p.xp for p in preds))
    floor = float(sum(p.xp_floor for p in preds))
    ceiling = float(sum(p.xp_ceiling for p in preds))

    drivers, fixtures = await _adv_drivers_and_fixtures(db, player, horizon)
    payload_drivers = [
        {"feature": n, "phrase": DRIVER_PHRASES.get(n, n), "direction": "up" if d >= 0 else "down"}
        for n, d in drivers
    ]

    cached = (await db.execute(select(XpRationale).where(
        XpRationale.player_id == player_id, XpRationale.gameweek_id == gw_id,
        XpRationale.model_version == mv,
    ))).scalar_one_or_none()
    if cached is not None:
        text, source = cached.text, "llm"
    else:
        pj = {"web_name": player.web_name, "position": player.position,
              "team_short": fixtures[0]["team_short"] if fixtures else ""}
        text = await generate_within_budget(
            db, "xp_explain",
            explanation_prompt(pj, fixtures, drivers, xp=xp_total, floor=floor,
                               ceiling=ceiling, horizon=horizon),
            max_output_tokens=160,
        )
        if text:
            db.add(XpRationale(player_id=player_id, gameweek_id=gw_id, model_version=mv,
                               text=text, model=get_settings().gemini_model))
            await db.commit()
            source = "llm"
        else:
            text = template_explanation(
                {"web_name": player.web_name, "position": player.position,
                 "team_short": pj["team_short"]},
                xp=xp_total, floor=floor, ceiling=ceiling, drivers=drivers, horizon=horizon)
            source = "template"
    return {"player_id": player_id, "web_name": player.web_name, "position": player.position,
            "model": mv, "xp_total": xp_total, "floor": floor, "ceiling": ceiling,
            "drivers": payload_drivers, "text": text, "source": source}
```
  Helper `_adv_drivers_and_fixtures(db, player, horizon)`:
  - load finished-GW `PlayerGwStat` for this player (minutes>0) oldest-first → `history` dicts.
  - `conceded` for this player's position vs each upcoming opponent: reuse the same
    `PlayerGwStat`-derived aggregate the worker builds, but filtered — simplest: query
    `PlayerGwStat` joined to finished `Gameweek`, group by `opponent_team_id` where the *scoring*
    player's position == `player.position` (need a Player join). Keep it to `wmean(vals[-5:], 5)`.
  - upcoming fixtures: `select(Fixture).join(Gameweek).where(Gameweek.finished.is_(False))
    .order_by(Gameweek.deadline_time).limit(horizon)`, keep those where the player's team is home
    or away; build `{"opponent_short","was_home","difficulty","team_short"}` (team short_names via a
    `{id: short}` map).
  - `row = adv_feature_row(history[-5:], was_home=<first fixture>, value=player.now_cost,
    opp_conceded_to_pos_5=<first opp>)`; if `None` → return `([], fixtures)`.
  - `adv = AdvancedXP.load(_adv_artifact_dir())` (reuse the worker's env var via a local
    `_adv_artifact_dir()` in `main.py`, or import from the worker — prefer a 2-line local copy
    reading `os.environ.get("FPLGURU_ADV_XP_ARTIFACT_DIR", get_settings().adv_xp_artifact_dir)`).
    `return (adv.explain_row(player.position, row, top=3), fixtures)`. Wrap the load in
    `try/except (FileNotFoundError, NotADirectoryError)` → `([], fixtures)`.
- [ ] Imports: `from fplguru_explain import DRIVER_PHRASES, explanation_prompt, template_explanation`,
  `from fplguru_ml.model_advanced import AdvancedXP`, `from fplguru_ml.serving import adv_feature_row`,
  `from fplguru_core.models import XpRationale`, `import os`.
- [ ] **Step 4:** `pytest services/api services/worker packages/ml -q` green; `ruff`; `alembic check`.
  Commit `feat(api): GET /players/{id}/xp/explain — cached LLM rationale for advanced xP`.

---

## Task 5: web — "Why?" on the squad view

**Files:** `apps/web/src/lib/api.ts` (+ one test in `api.entries.test.ts` or a new
`api.explain.test.ts`), `apps/web/src/app/squad/SquadTable.tsx`.

- [ ] `api.ts`:
```ts
export type XpExplain = {
  player_id: number; web_name: string; model: string;
  xp_total: number; floor: number; ceiling: number;
  drivers: { feature: string; phrase: string; direction: "up" | "down" }[];
  text: string; source: "llm" | "template";
};
export function getXpExplain(base: string, playerId: number, horizon = 3, model: XpModel = "advanced") {
  return fetch(`${base}/players/${playerId}/xp/explain?horizon=${horizon}&model=${model}`,
    { cache: "no-store" }).then(asJson<XpExplain>);
}
```
  test: asserts the URL contains `/players/11/xp/explain?horizon=3`.
- [ ] `SquadTable.tsx`: add a trailing column with a small ghost `Button` "Why?" that toggles an
  `expandedId` state; when expanded, render a row below (or a `<details>`-style panel under the
  Card) showing `text`, a line of driver chips (`Badge variant={d.direction === "up" ? "positive"
  : "danger"}` with `d.phrase` and ↑/↓), and a muted `source` tag. Fetch lazily on first expand,
  cache in a `Record<number, XpExplain>` in state; show a `Skeleton` while loading. Guard: the
  "Why?" button only when `model === "advanced"` (explain is adv-only) — else hide it.
- [ ] `vitest run` → 21 passed; `next build` → success.
  Commit `feat(web): per-player "Why?" xP explanation on the squad view`.

---

## Task 6: docs

- [ ] `README.md` — under the xP section, a short "Explanations (`adv-v1`)" note: occlusion
  attribution → drivers → Gemini (`generate_within_budget`, `xp_explain` feature, cached in
  `xp_rationale`) with a template fallback; `GET /players/{id}/xp/explain?horizon=&model=`.
- [ ] `docs/plans/2026-08-27-fplguru-master-build-plan.md` — **P2c ✅** row (paths, what shipped,
  deferred: worker pre-warm of rationales, SHAP proper, per-GW drivers); decrement the count line;
  note P2c no longer blocks anything new (P2d/P2f already unblocked by P2b).
- [ ] `docs/RESUME-foundation.md` — top line + a `## P2c` section (task table, the "xG drivers are
  0 until PitchAPI id-mapped, so drivers lean on form/fixture/minutes" caveat, artifact retrain
  note).
- [ ] Full sweep: `pytest -q -W error`, `ruff check .`, `alembic check`, web `vitest` + `build`.
  Commit `docs: P2c LLM explanation layer complete`.

---

## Self-Review

**Spec coverage (master §5.4 / §5.2):** "turns Advanced model output + top features into
plain-English rationale" → `explain_row` occlusion drivers + `explanation_prompt` + Gemini via
`generate_within_budget`, cached (`xp_rationale`), template fallback (Tasks 1,2,4). **SHAP proper**
is still deferred — occlusion-at-median is the cheap stand-in and is labelled as such. Budget ledger
+ monthly cap reused from P2e (no new budget code). No tier gate (2026-08-27 pivot).

**Migration:** one `create_table` (`0012`), no JSON `server_default` → `alembic check` stays clean;
exact-set models test updated.

**Consistency:** `DRIVER_PHRASES` keys ⊆ `FEATURE_NAMES_ADV`; `adv_feature_row` (shared
`fplguru_ml.serving`) used by both worker and the new endpoint so served drivers match served xP;
`model_version` `"adv-v1"` string consistent (`_ADV_MODEL_VERSION`, cache key, retrained
`meta.json`); `explain_row` returns `list[tuple[str, float]]` consumed identically in the API
payload builder and the template helper.

**Placeholder scan:** Task 4's `_adv_drivers_and_fixtures` is described as steps, not full code —
it reuses established query patterns (`PlayerGwStat`/`Fixture`/`Gameweek` joins already in
`compute_and_store_xp` and `/fdr`); acceptable. Tasks 1–3 + the endpoint body are complete code.

**Retrain risk:** adding `feature_medians` to `meta.json` is additive; `AdvancedXP.load` uses
`meta.get("feature_medians", {})` so old artifacts still load (explain then returns `[]` → template
still works). Commit the retrained `meta.json`.

---

## Execution Handoff

Branch `feature/p2c-llm-explanation` off `main`. Subagent-driven, order 1 → 6. Tasks 1 & 4 get a
full review; 2, 3, 5 spec-check + quality-check; 6 spec-check. After Task 6: whole-branch review,
PR → `main`, watch CI, squash-merge.

### Deferred follow-ups
- Worker pre-warm: generate + cache rationales for high-ownership players on a Beat task.
- Real SHAP / tree-path attribution (shared with P4b), replacing occlusion-at-median.
- Per-horizon-GW drivers (currently one explanation for the whole horizon).
- Surface the same explanation on the (future) player detail page and in `/captain`.
