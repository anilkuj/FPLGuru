# FPLGuru Foundation — Resume / Handoff

**Status:** ✅ Foundation (PR #1), ✅ P1c Basic xP (PR #2), ✅ P1a Team Linking (PR #3), ✅ P1d FDR Table (PR #4), ✅ P1b Live Scores (PR #5) — merged to `main`. **P1e Alerts Engine built on `feature/p1e-alerts`** (Tasks 1–7 done, Task 8 docs finishing; not yet pushed). Scope pivot 2026-08-27: product is **free, no Free/Pro tiers** — P1g (Stripe) + P4c (annual billing) dropped; P1a-auth optional; `alert_cap` is user-configurable (default uncapped), no "upgrade" message.
**Last updated:** 2026-08-27.
**Branch:** `feature/p1e-alerts` (off `main`), not pushed.

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
| 8 | `model_basic.py` — `BasicXP` per-position bundle + `baseline()` cold start | ✅ `bc06725` / `b4bfd22` |
| 9 | `backtest.py` — walk-forward MAE/RMSE vs baseline | ✅ `ac60904` |
| 11 | `scripts/train_xp.py` + `scripts/backtest_xp.py` | ✅ `def9424` |
| — | real `basic-v1` artifacts + backtest report (all positions beat baseline) | ✅ `622371e` / `e69a1a0` |
| 12 | `compute_xp` worker task (+ cold-start fallback 12b) | ✅ `1f02014` / `601b0af` / `b4bfd22` |
| 13 | `GET /xp` + `GET /players/{id}/xp`; `/status` enumerates all sources | ✅ `daa0fd8` |
| 14 | beat wiring, README, master-plan status | 🔧 finishing |

**Live end-to-end verified:** `sync_gw_stats` → 610 `player_gw_stats`; `compute_xp` → 2,465 `player_gw_predictions`; `GET /xp?horizon=5` → 493 players ranked (top: Raya GK ~11 xP); `/status` → all 4 sources `ok`. **Merged to `main` as PR #2 (`ab2c266`).**

---

## P1a — Team Linking & Dashboard Shell (branch `feature/p1a-team-dashboard`)

Plan: [`docs/plans/2026-08-27-p1a-team-dashboard.md`](plans/2026-08-27-p1a-team-dashboard.md). **No auth in this sub-plan** — entry-id-keyed; accounts (email/pw or Google) are sub-plan **P1a-auth**, blocked on the OAuth-creds / email-transport decision.

| Task | What | Status |
|---|---|---|
| 1 | `linked_teams` / `entry_gw_history` / `entry_picks` + `0003` migration | ✅ `acc85af` |
| 2 | `FplClient.entry` / `entry_history` / `entry_picks` | ✅ `a0619dd` |
| 3 | `normalize_entry` / `_history` / `_picks` | ✅ `1640aed` |
| 4 | `fplguru-entrysync` pkg + `sync_entry` + `sync-linked-teams` Beat | ✅ `f839196` |
| 5 | `POST /link/{id}`, `GET /entries/{id}` (squad + xP), `GET /entries/{id}/history` | ✅ `250daa7` |
| 7 | web: typed entry client + `localStorage` entry id | ✅ `cac8756` |
| 8 | web: nav shell + link form + squad page | ✅ `2224e8c` |
| 9 | docs + wiring | 🔧 finishing |

**Live-verified:** `POST /link/1` → "Chris Musson"; `GET /entries/1` → 15 picks with xP (Raya GK 11.0, Tzolis MID 9.5); `GET /entries/1/history` → GW1 (41 pts). 87 py tests + 3 web tests, `-W error` / `ruff` / `alembic check` clean, `next build` clean. Next: review → PR `feature/p1a-team-dashboard` → `main`.

**Remaining unblocked Phase-1 path:** P1f (deadline reminders — extends P1e's alert channel) → P1h (PWA — `manifest.json`, service worker, VAPID + push-subscription mgmt, Web Push delivery sink for P1e alerts). Blocked: P1a-auth (OAuth/email — optional, blocks nothing). P1g (Stripe) and P4c (annual billing) **dropped** — product is free, no tiers.

**P1c notes:** hand-rolled ridge (no scikit-learn — dodges SAC native-binary block); Basic model is FPL-data-only + leak-safe features (rolling form, minutes, home/away, price, opp-conceded-to-position); component breakdown (`x_*` cols) left 0.0 for Basic, filled in Advanced (P2b). Test seeding must be **FK-parent-first** (models have no `relationship()` → single `add_all` flushes in alphabetical class order). Real training/backtest needs `python scripts/fetch_historical.py 2022-23 2023-24 2024-25` first (gitignored `data/historical/`). New `DataSyncLog.source` values `fpl_gw_stats` / `xp_compute` — Task 14 must extend `/status`'s hardcoded source tuple (or make it enumerate `distinct(source)`).

**Final review notes (all 14 tasks green):** 34 tests pass deterministically under `-W error`, 0 skips; no model↔migration drift (`alembic check` clean); env-var naming consistent; no secrets. The one blocker was `ruff check .` (never run locally due to SAC) → 39 errors that would red the CI `python` job. Being fixed now. Non-blocking follow-ups: `apps/web` manifest references icon PNGs that don't exist yet (deferred to sub-plan P1h), create-next-app scaffold SVGs unused, a test that runs `alembic upgrade head` against the test DB would close the create_all-vs-migrations gap.

**Test state:** `python -m pytest -q` (repo root) → **~33 passed, 0 warnings** (exact count grows per task). Requires Docker Postgres up.

---

## P1d — FDR Table (branch `feature/p1d-fdr`)

Plan: [`docs/plans/2026-08-27-p1d-fdr-table.md`](plans/2026-08-27-p1d-fdr-table.md). Subagent-driven, same process.

| Task | What | Status |
|---|---|---|
| 1 | `packages/fdr` (`fplguru-fdr`) — pure `compute_fdr(teams, fixtures, gameweeks, *, start_gw, horizon)` | ✅ `9b02cd1` |
| 2 | `GET /fdr?horizon=&start_gw=` API (`fplguru-fdr` added to `services/api` deps) | ✅ `bd7f90b` |
| 3 | web `/fdr` colour-coded grid + horizon `<select>` + `prefs.ts` localStorage + nav link | ✅ `408fdec` |
| 4 | docs (README, master plan ✅, this file) + final verification | 🔧 finishing |

**FDR model:** per fixture, opponent venue strength → strength-tier FDR (`None`→3.0, else `1 + 4·clamp((s−2)/3)`); if the opponent has ≥1 finished result, blend 55/45 with goals form against a pooled scored+conceded per-game baseline; split into `att_fdr` (facing their attack → your clean-sheet difficulty) and `def_fdr` (facing their defence → your scoring difficulty); `fdr = mean(att, def)` (stored unrounded), `band = round(fdr)` clamped 1–5. Teams sorted easiest-first by `avg_fdr` (None last). No tier gate — horizon 1–10 for everyone.

**Implementer caught 2 real bugs in the plan's verbatim Task 1 code:** `round(fdr, 2)` broke an exact-arithmetic test assertion (→ store `fdr` unrounded); baseline = mean(goals-for only) mis-ordered att/def (→ pool both scored and conceded per-game). Plan's Task 1 code block + test count synced on disk (`45b119c`).

**Verification (repo state after Task 3):** `python -m pytest -q` → **93 passed**, no warnings; `ruff check .` clean; `alembic check` clean (P1d adds no tables); `pnpm --filter web test` → 4 passed; `pnpm --filter web build` → `/fdr` prerendered OK. **Merged to `main` as PR #4 (`8b4dbc2`).**

---

## P1b — Live Scores & GW Live (branch `feature/p1b-live-scores`)

Plan: [`docs/plans/2026-08-27-p1b-live-scores.md`](plans/2026-08-27-p1b-live-scores.md). Executed inline by the coordinator (the first Task-1 subagent died on a session limit; remaining tasks done directly), same TDD + full-verification discipline.

| Task | What | Status |
|---|---|---|
| 1 | `packages/live` (`fplguru-live`) — `project_bonus` (rank-position tie rule) + `build_live_rows` | ✅ `f13b1ac` |
| 2 | `player_gw_live` table + `fixtures.started/finished_provisional/minutes` (`0004`) + `normalize_fixtures` | ✅ `fe519b0` |
| 3 | worker `_poll_live` + `poll_live` task + `poll-live` Beat entry + `live_poll_seconds`/`live_stream_poll_seconds` settings | ✅ `6037c5c` |
| 4+5 | `GET /gameweeks/current/live` snapshot + `GET /gameweeks/current/live/stream` (hand-rolled SSE) | ✅ `c8fac65` |
| 6+7 | web `getLive` + types; `/live` page + `LiveBoard` (EventSource + 15s poll fallback + my-players filter); nav link | ✅ `d9642e4` |
| 8 | docs (README GW Live section + endpoints, master plan ✅, this file) + final verification | 🔧 finishing |

**Bonus model:** `project_bonus({player_id: bps})` → standard-competition rank of positive BPS; rank 0→+3, 1→+2, 2→+1 (so BPS 30, 30, 25 → +3, +3, +1). `build_live_rows` groups by `explain[].fixture` (DGW-safe, bonus summed across a player's fixtures); when `explain` is absent it falls back to one synthetic bucket keyed on `stats.bps`. `poll_live` only calls `event/{gw}/live` when a current-GW fixture has `started and not finished`; otherwise it just refreshes fixture scores/state and writes an `ok` audit row.

**Deviations from the plan:** Tasks 4 and 5 landed in one commit (they share `_live_snapshot`). The SSE test drives the `_live_event_stream` async generator directly + asserts the route's media-type/headers — httpx's `ASGITransport` buffers responses so it cannot consume a real stream. `is_disconnected()` is checked *after* the first `yield` (a pre-yield check can block under some Starlette versions). Env prefix is `FPLGURU_` so the Beat cadence var is `FPLGURU_LIVE_POLL_SECONDS`.

**Verification (repo state after Task 7):** `python -m pytest -q -W error` → **109 passed**, no warnings; `ruff check .` clean; `alembic check` clean; web `vitest run` → 5 passed; `next build` → `/live` prerendered OK. **Merged to `main` as PR #5 (`0e7b7d1`).** **Live end-to-end (real FPL data during a match window) not yet verified** — do this once a GW is in play.

---

## P1e — Alerts Engine + Priority Ranking (branch `feature/p1e-alerts`)

Plan: [`docs/plans/2026-08-27-p1e-alerts-engine.md`](plans/2026-08-27-p1e-alerts-engine.md). Design: [`docs/design/2026-08-27-alert-priority-ranking.md`](design/2026-08-27-alert-priority-ranking.md). Executed inline by the coordinator, TDD + full-verification per task.

| Task | What | Status |
|---|---|---|
| 1 | priority-ranking design doc | ✅ `2592eb4` |
| 2 | `packages/alerts` (`fplguru-alerts`) — `score_alert` + `availability_alerts` + `dgw_bgw_alerts` | ✅ `5c53ffb` |
| 3 | `alerts` table + `linked_teams.alert_cap` (`0005`) | ✅ `bfe4e70` |
| 4 | worker `_generate_alerts` + `generate_alerts` task + `generate-alerts` Beat (30 min) + cap application | ✅ `c9f70f7` |
| 5 | `GET /entries/{id}/alerts`, `POST .../alerts/seen`, `PATCH .../settings` | ✅ `cf9eb9d` |
| 6+7 | web `getAlerts`/`markAlertsSeen`/`updateEntrySettings` + `/alerts` feed page + `NavAlerts` unseen badge | ✅ `e148580` |
| 8 | docs (README Alerts section, master plan ✅, this file) + final verification | 🔧 finishing |

**Model:** `score_alert` = additive terms (base 60 availability / 45 bgw / 40 dgw; +25 (vice-)captain, +15 XI, +15 hard-out i/s/u, +10 pre-deadline), clamped 0–100, ties by `id`. `availability_alerts` flags any owned pick with `status != 'a'` or `chance_of_playing_next_round < 100`; dedup key encodes status+chance so a change re-alerts. `dgw_bgw_alerts` uses a `{team_id: fixture_count}` map for the current GW — **absent team = 0 fixtures = blank** — and the worker only runs it once at least one GW fixture is loaded (guards against a false BGW storm before `sync_fixtures`). Cap: per team per GW, sort by `(-priority, id)`, `suppressed = index >= alert_cap` (NULL cap → nothing suppressed).

**Deviations from the plan:** `dgw_bgw_alerts`'s `fixture_counts.get(team_id, 0)` (plan first draft had default `1`, which hid real blanks) + the worker `sum(fx_counts.values()) > 0` guard. Web feed type is `AlertFeedData` (not `AlertFeed`, to avoid clashing with the `AlertFeed` component). API mutations use `await db.commit()` (not `async with db.begin()` — the session already autobegan on the `_linked_or_404` read). "Mark all read" (no `ids`) only clears the visible feed, not suppressed rows. Tasks 6+7 in one commit.

**Verification (repo state after Task 7):** `python -m pytest -q -W error` → **126 passed**, no warnings; `ruff check .` clean; `alembic check` clean; web `vitest run` → 7 passed; `next build` → `/alerts` prerendered OK. Next: docs commit → PR `feature/p1e-alerts` → `main`. **Live end-to-end not yet verified** (needs linked teams + a real availability change or DGW/BGW GW).

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
