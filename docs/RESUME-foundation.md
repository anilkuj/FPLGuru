# FPLGuru Foundation — Resume / Handoff

**Status:** ✅ **Foundation complete, PR green.** All 14 tasks + final review + ruff cleanup. **PR [anilkuj/FPLGuru#1](https://github.com/anilkuj/FPLGuru/pull/1)** (`feature/foundation` → `main`) — CI `python` + `web` both ✅, `mergeStateStatus: CLEAN`. Ready to merge (needed a Node 20→22 bump for jsdom 30 / undici 8).
**Last updated:** 2026-08-27.
**Branch:** `feature/foundation` (~42 commits ahead of `main`), pushed to `origin`.

---

## What this is

Executing [`docs/plans/2026-08-27-foundation.md`](plans/2026-08-27-foundation.md) — the "Foundation" sub-plan of the FPLGuru build (repo/infra + FPL data pipeline: monorepo, Postgres/Redis, SQLAlchemy models, Alembic, resilient FPL API client, ingest normalizers, Celery worker on a Beat schedule, FastAPI read API, historical-data loader, CI, Next.js PWA shell).

Method: **superpowers:subagent-driven-development** — one implementer subagent per task, then a spec-compliance review and a code-quality review, fix loop, commit, next task.

The master roadmap for everything *after* Foundation is [`docs/plans/2026-08-27-fplguru-master-build-plan.md`](plans/2026-08-27-fplguru-master-build-plan.md) (22 sub-plans; Foundation is sub-plan "F").

---

## Progress

| Task | What | Status | Key commit(s) |
|---|---|---|---|
| 1 | Repo & package scaffold (venv + editable installs) | ✅ | `5feb5ce`, `7fd4950` |
| 2 | Local `docker-compose` infra + `fplguru_core.settings` | ✅ | `f54f6b9`, `3cb81c6` |
| 3 | Core SQLAlchemy models + `db.py` (`reset_state`, `dispose_engine`) | ✅ | `81ff226`, `7176928` |
| 4 | Alembic async migrations + shared Postgres test fixtures | ✅ | `1e76a4f`, `5e3145d` |
| 5 | Resilient async `FplClient` (retry/backoff, 429/408, redirects) | ✅ | `bf9cb98`, `5b11a82` |
| 6 | Pure FPL bootstrap/fixtures normalizers | ✅ | `0f7b26c` |
| 7 | Celery worker: `_upsert`, `sync_bootstrap`/`sync_fixtures`, Beat | ✅ | `73c10b8`, `539296a` |
| 8 | `sync_fixtures` test + Beat-wiring test | ✅ | `397b357` |
| 9 | Graceful-degradation error-path tests (now test-only) | ✅ | `0723ce1` |
| 10 | FastAPI service (`/health` `/ready` `/gameweeks` `/gameweeks/current` `/status`) | ✅ | `990549b`, `b78e1ae` |
| 11 | Historical `merged_gw` normalizer + `scripts/fetch_historical.py` | ✅ | `79dd0cc` (+ numpy pin follow-up) |
| 12 | CI pipeline (`.github/workflows/ci.yml`) | ✅ | `55e951e` |
| 13 | Next.js PWA shell (`apps/web/`, Next 16.3.3 / React 19 / Tailwind v4 / Vitest 4) | ✅ | `e00346b` |
| 14 | `README.md` + acceptance checklist (+ `sync_all()` one-loop populate helper) | ✅ | `d14fc23` |
| — | Final whole-branch review | ✅ | verdict: READY AFTER BLOCKING FIXES |
| — | Fix 39 `ruff` errors (isort/bugbear config, line wraps, B904, dead noqa) | ✅ | `803e731` |
| — | Push branch + open PR #1 → `main` | ✅ | — |
| — | CI on PR #1 (Node 20→22 fix) | ✅ green | `4e...` |
| — | Merge PR #1 → `main` | ✅ squash-merged `2cff1b5` | — |

---

## P1c — Basic xP engine (in progress, branch `feature/basic-xp`)

Plan: [`docs/plans/2026-08-27-p1c-basic-xp-engine.md`](plans/2026-08-27-p1c-basic-xp-engine.md). Executing subagent-driven, same process.

| Task | What | Status |
|---|---|---|
| 1 | `fplguru-ml` deps (numpy<2.5 / pandas<4) | ✅ `7530e3a` |
| 2 | `player_gw_stats` / `_features` / `_predictions` tables + `0002` migration | ✅ `6032f62` |
| 3 | `FplClient.event_live` + `normalize_event_live` | ✅ `225a597` |
| 4 | `sync_gw_stats` worker task (per-GW actuals) | ✅ `6ef3068` |
| 6 | `features.py` — `FEATURE_NAMES` + `feature_row_from_history` (recency-weighted) | ✅ `e57b4a8` |
| 5 | `frame.py` — leak-free historical training frame | ✅ `18c8bf9` |
| 7 | `ridge.py` — closed-form ridge, JSON persistence (no sklearn) | ✅ `a553e0e` |
| 10 | `rollout.py` — multi-GW horizon + widening band | ✅ `161da84` |
| 8 | `model_basic.py` — `BasicXP` per-position bundle | 🔧 in progress |
| 9 | `backtest.py` — walk-forward MAE/RMSE vs baseline | ⬜ |
| 11 | `scripts/train_xp.py` + `scripts/backtest_xp.py` | ⬜ |
| 12 | `compute_xp` worker task | ⬜ |
| 13 | `GET /xp` + `GET /players/{id}/xp` | ⬜ |
| 14 | beat wiring, README, master-plan status | ⬜ |

**P1c notes:** hand-rolled ridge (no scikit-learn — dodges SAC native-binary block); Basic model is FPL-data-only + leak-safe features (rolling form, minutes, home/away, price, opp-conceded-to-position); component breakdown (`x_*` cols) left 0.0 for Basic, filled in Advanced (P2b). Test seeding must be **FK-parent-first** (models have no `relationship()` → single `add_all` flushes in alphabetical class order). Real training/backtest needs `python scripts/fetch_historical.py 2022-23 2023-24 2024-25` first (gitignored `data/historical/`). New `DataSyncLog.source` values `fpl_gw_stats` / `xp_compute` — Task 14 must extend `/status`'s hardcoded source tuple (or make it enumerate `distinct(source)`).

**Final review notes (all 14 tasks green):** 34 tests pass deterministically under `-W error`, 0 skips; no model↔migration drift (`alembic check` clean); env-var naming consistent; no secrets. The one blocker was `ruff check .` (never run locally due to SAC) → 39 errors that would red the CI `python` job. Being fixed now. Non-blocking follow-ups: `apps/web` manifest references icon PNGs that don't exist yet (deferred to sub-plan P1h), create-next-app scaffold SVGs unused, a test that runs `alembic upgrade head` against the test DB would close the create_all-vs-migrations gap.

**Test state:** `python -m pytest -q` (repo root) → **~33 passed, 0 warnings** (exact count grows per task). Requires Docker Postgres up.

---

## Environment (READ THIS BEFORE RESUMING)

The dev machine has **Smart App Control (SAC) ON**. SAC blocks unsigned/unknown native binaries — this forced several deviations:

| Thing | Decision |
|---|---|
| `uv` | **Blocked by SAC.** Plan reworked to plain **`venv` + `pip`**. Every tool is invoked `python -m <tool>` (`python -m pytest`, `python -m alembic`, `python -m uvicorn`, `python -m celery`). Never a bare `pytest`/`ruff` exe. |
| Python | **3.12.10** from python.org, reachable only as **`py -3.12`** (bare `python` = Windows Store stub until a venv is active). A separate 3.14 is also installed — always pin `py -3.12`. |
| venv | `.venv/` at repo root. Create with `py -3.12 -m venv .venv`. After activation, `python` = the venv's 3.12. |
| deps | One root `requirements-dev.txt` = `-e ./packages/*` + `-e ./services/*` + test deps. Each package's own deps live in its `pyproject.toml`. Root `pyproject.toml` is config-only (pytest + ruff). |
| `ruff` | Runs in CI. **Also works locally** via `python -m ruff` (`ruff`'s bundled binary is NOT SAC-blocked — only `uv.exe` was). `python -m pip install "ruff==0.6.*"` if you want it in the venv. |
| `pnpm` | Not installed. Get it in Task 13 via `corepack enable` (Node 25 is present). |
| Docker | Docker Desktop installed & running. Compose project name is **`fplguru`** (`docker compose -f infra/docker-compose.yml ...`), containers `fplguru-postgres-1` / `fplguru-redis-1`. |
| `numpy` | **SAC blocks `numpy` 2.5.x** (`numpy/random/_sfc64.pyd` → "Application Control policy has blocked this file"), which breaks `import pandas`. Pinned `numpy>=2.2,<2.5` in `packages/ingest/pyproject.toml`. 2.2.6 works. |
| `@next/swc` (Task 13) | Turned out fine — Next 16's `next build` uses Turbopack (no `@next/swc` Rust addon) and ran clean locally. If a future create-next-app version pins a build that *does* trip SAC, ship the web build CI-only. Never disable SAC. |
| General SAC pattern | Any new dependency that ships a native `.pyd`/`.dll`/`.node` may be blocked *per-file* by reputation. Symptom: `ImportError: ... An Application Control policy has blocked this file`. Fix: pin to an older version of that package whose binary SAC trusts. Never disable SAC. |

### To get a working environment from a fresh clone / new session

```bash
cd D:/AntiGravity/FPLGuru
git checkout feature/foundation

docker compose -f infra/docker-compose.yml up -d --wait

py -3.12 -m venv .venv
source .venv/Scripts/activate        # Git Bash;  PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

python -m alembic upgrade head
python -m pytest -q                  # expect all green
```

---

## Execution protocol (for the coordinator / whoever resumes)

1. **One implementer subagent per task.** Paste the FULL task text from the plan into the subagent prompt — never make it read the plan file. Include the "Environment" facts above as scene-setting.
2. **After each implementer reports DONE:** run a **spec-compliance** review (verify files are verbatim to the plan, tests pass, nothing extra), then a **code-quality** review. For the mechanical tasks (12 partly, 14) a single combined spec+quality pass is fine; for anything with real logic do both.
3. **Fix loop:** send review findings back to the *same* implementer subagent (via SendMessage to its agent id) to fix, then re-verify. Repeat until clean.
4. **Commits:** implementers stage with **`git add -A -- ':!docs'`** (the `':!docs'` matters — the coordinator edits the plan doc concurrently and it must not get swept into task commits). Commit author: `git -c user.name="Anil Kujur" -c user.email="anilkuj@gmail.com" commit -m "<msg>" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`. **Do not push.**
5. **Plan doc is living:** when a review changes a task's approach, update `docs/plans/2026-08-27-foundation.md` to match and commit it as a separate `docs:` commit. The plan doc currently reflects all applied changes through Task 11.
6. **After Task 14:** run one final review over the whole branch diff, then use **superpowers:finishing-a-development-branch** to merge `feature/foundation` → `main` (user wants merge-to-main at the end; a GitHub PR is optional).

---

## Key deviations from the plan's first draft (all now reflected in the plan doc)

- **`uv` → `venv`/`pip`** everywhere (SAC). CI uses `actions/setup-python` + pip, not `astral-sh/setup-uv`.
- **DB test fixtures are opt-in** (Task 4): only tests requesting `db_session`/`db_engine` touch Postgres; pure-unit tests need no Docker. The engine fixture is named **`db_engine`** (was `_engine`). Cleanup + `db.dispose_engine()` happen in `db_session` teardown (no autouse `_clean_tables`). Autouse `_point_app_at_test_db` points app code at `fplguru_test` + `reset_state()`.
- **`fplguru_core.db`** gained `reset_state()` (clears settings+engine+sessionmaker lru_caches) and `dispose_engine()`; `session_scope` is now an `@asynccontextmanager`.
- **Models** (Task 3): natural-key PKs (`Team/Gameweek/Player/Fixture.id`) are `autoincrement=False`; `Base.metadata` has a `naming_convention` (FK token is `referred_table_name`, not `referent_`); `news`/`detail` have `server_default=""`.
- **Alembic** (Task 4): `env.py` sets URL from `get_settings()`, `compare_type=True` + `compare_server_default=True`; CI runs `alembic check` as a model↔migration drift guard; `[tool.ruff.lint.per-file-ignores]` `"alembic/*" = ["E402"]`.
- **`FplClient`** (Task 5): split `httpx.Timeout`, `follow_redirects=True`, non-JSON body → `FplApiError`, 429/408 retried, `stop_after_delay(30)` ceiling, `async with` support, `before_sleep_log`.
- **Worker** (Task 7): the Celery task wrappers call `asyncio.run(_run_and_dispose(...))` which disposes+resets the process-cached async engine after every run (fixes a real prefork event-loop-reuse bug). Error rows written on a **fresh** session via `_log_error`. `_sync_fixtures` skips (records "ok/skipped") when `teams` is empty. `_upsert` guards against columns missing from the row dict. **Deploy note: worker must run `-P prefork` or `-P solo`.**
- **Task 9** is now **test-only** — fetch-failure error logging moved into Task 7's `_log_error`.
- **API** (Task 10): added `/ready` (DB `SELECT 1` → 200/503); `get_db` documented read-only; `fastapi>=0.111,<1`.
- **Task commits** exclude `docs/` via `git add -A -- ':!docs'`.
- **Plan test snippets** that passed bare ISO strings for `DateTime(timezone=True)` columns were fixed to real `datetime(...)` objects (asyncpg rejects strings for timestamptz).

---

## Remaining work

### Task 14 — README + acceptance checklist
`README.md` (drafted in the plan; keep the `py -3.12` / venv / `python -m` conventions). Then walk the acceptance checklist against a real run.

### Then
Final whole-branch review → merge `feature/foundation` → `main`.

---

## Open items / risks

- **Task 13 SAC**: `next build` may not run locally. Mitigation: CI-only web build.
- **CI is untested** until pushed — the `.github/workflows/ci.yml` service-container + `fplguru_test` DB creation path (the `db_engine` fixture creates the DB) hasn't run on GitHub Actions yet.
- **No lockfiles** on the Python side — deps are `>=` ranges (pydantic/fastapi have `<次` upper bounds; others don't). A constraints file was noted as a follow-up, not done.
- **`pytest-xdist` unsupported** — single shared `fplguru_test` DB + truncate-after. Documented in `conftest.py`.
- Nothing is pushed. `origin/main` still only has the two plan docs from the very first commit.
