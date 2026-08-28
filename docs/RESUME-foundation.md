# FPLGuru Foundation — Resume / Handoff

**Status:** **PHASE 1 COMPLETE** + **P2h + P2i shipped.** ✅ F (#1), P1c (#2), P1a (#3), P1d (#4), P1b (#5), P1e (#6), P1f (#7), P1h (#8), P2h (#9) merged to `main`. **P2i Free Tools Suite built on `feature/p2i-free-tools`** (Tasks 1–5 done, Task 6 docs finishing; not yet pushed). Scope pivot 2026-08-27: product is **free, no Free/Pro tiers** — P1g + P4c dropped; P1a-auth optional. **xG source decided 2026-08-27 → PitchAPI** (`pitchapi.dev`, `X-API-KEY`, test key held by user in `FPLGURU_PITCHAPI_KEY` — never committed; opaque `p_` player ids need fuzzy FPL mapping) — **P2a is now unblocked.** Still blocked: LLM provider + monthly budget (P2c/P2e/P3a-c), Telegram bot token (P2g). **Unblocked Phase-2 next:** P2a (PitchAPI ingestion), P2d optimizer, P2f H2H.
**Last updated:** 2026-08-27.
**Branch:** `feature/p2i-free-tools` (off `main`), not pushed.

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

**Phase 1 is complete** (P1a, P1b, P1c, P1d, P1e, P1f, P1h). Optional leftover: P1a-auth (OAuth/email — blocks nothing). P1g (Stripe) + P4c (annual billing) **dropped**. Phase 2 next — see the status line at the top for which parts are blocked on decisions.

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

**Verification (repo state after Task 7):** `python -m pytest -q -W error` → **126 passed**, no warnings; `ruff check .` clean; `alembic check` clean; web `vitest run` → 7 passed; `next build` → `/alerts` prerendered OK. **Merged to `main` as PR #6 (`a62aa3b`).** **Live end-to-end not yet verified** (needs linked teams + a real availability change or DGW/BGW GW).

---

## P1f — Deadline Reminders (branch `feature/p1f-deadline-reminders`)

Plan: [`docs/plans/2026-08-27-p1f-deadline-reminders.md`](plans/2026-08-27-p1f-deadline-reminders.md). Executed inline, TDD per task.

| Task | What | Status |
|---|---|---|
| 1 | `linked_teams.reminder_offsets` JSON column + `DEFAULT_REMINDER_OFFSETS` constant (`0006`) | ✅ `4f...`* |
| 2 | `fplguru_alerts.deadline_reminder_alerts` + `_BASE["deadline"] = 55` + ≤60-min tight bump | ✅ |
| 3 | `generate_alerts` calls it for the nearest-future-deadline GW; cap pass now loops distinct GW ids | ✅ |
| 4 | `GET` + `PATCH /entries/{id}/settings` accept `reminder_offsets` (sanitised: >0, ≤4320, ≤7) | ✅ |
| 5 | web: `getEntrySettings` + options-object `updateEntrySettings`; presets + free-text editor on `/alerts` | ✅ |
| 6 | docs (README, master plan ✅, this file) + final verification | 🔧 finishing |
*see `git log feature/p1f-deadline-reminders` for exact SHAs.

**Model:** `deadline_reminder_alerts(deadline, now, offsets, *, gameweek_id)` emits one alert per offset whose window already contains `now` (`minutes_left <= offset`), dedup key `deadline:{gw}:{offset}` so each fires once. `score_alert` adds `type == "deadline"` → base 55, +15 when `minutes_left <= 60`, +10 pre-deadline (always true for these). The worker picks the Gameweek with the smallest `deadline_time > now` (works between GWs and mid-GW).

**Deviations from the plan:** `reminder_offsets` is DB-**nullable** with a Python-side `default` (no `server_default`) — a JSON `server_default` makes `alembic check` blow up on `'…'::json = '…'` (json has no `=` operator). `DEFAULT_REMINDER_OFFSETS = (1440,120,60,30)` lives in `fplguru_core.models`; readers coalesce `x or list(DEFAULT_REMINDER_OFFSETS)`. The three existing `test_generate_alerts` assertions gained `deadline:9:1440` (the P1e `_seed` deadline is ~24h out, so the 1440 reminder fires). Web `updateEntrySettings` changed shape → `(base, id, {alertCap, reminderOffsets})`; only caller updated in the same task.

**Verification (repo state after Task 5):** `python -m pytest -q -W error` → **135 passed**, no warnings; `ruff` clean; `alembic check` clean; web `vitest run` → 9 passed; `next build` → `/alerts` prerendered OK. **Merged to `main` as PR #7 (`9da2095`).**

---

## P1h — PWA (branch `feature/p1h-pwa`)

Plan: [`docs/plans/2026-08-27-p1h-pwa.md`](plans/2026-08-27-p1h-pwa.md). Executed inline, TDD per task.

| Task | What | Status |
|---|---|---|
| 1 | `scripts/gen_icons.py` (zlib-only PNG writer) + committed `icon-192/512.png` | ✅ |
| 2 | `push_subscriptions` table + `alerts.pushed_at` + `vapid_*` settings (`0007`) | ✅ |
| 3 | `packages/push` (`fplguru-push`) — `pending_push_targets` + `notification_payload` | ✅ |
| 4 | worker `_deliver_push` + `deliver_push` task + `deliver-push` Beat (60s); `_send_web_push` guarded (optional `pywebpush`), `PushGone` prunes dead endpoints | ✅ |
| 5 | `GET /push/vapid-public-key`, `POST`/`DELETE /entries/{id}/push/subscribe` | ✅ |
| 6 | `public/sw.js` (precache shell, network-first API cache, push/notificationclick) + `PwaSetup` install prompt + `viewport` themeColor | ✅ |
| 7 | `lib/push.ts` (`getVapidKey`/`subscribePush`/`unsubscribePush`) + `PushToggle` on `/alerts`; `asJson` exported from `api.ts` | ✅ |
| 8 | docs (README PWA section, `.env.example` VAPID vars, master plan ✅, this file) | 🔧 finishing |
See `git log feature/p1h-pwa` for exact SHAs.

**Push send is deploy-only.** `pywebpush` (→ `cryptography` + `aiohttp`) is deliberately **not** in `requirements-dev.txt` — SAC blocks that native tree on the dev box, and there's no HTTPS/real-subscription path to test it here anyway. `_send_web_push` imports it lazily; with no `FPLGURU_VAPID_PRIVATE_KEY` (the default) it logs and returns, and `_deliver_push`'s orchestration (targeting, `pushed_at` marking, 404/410 subscription pruning) is fully unit-tested with `_send_web_push` monkeypatched. To activate in production: `pip install pywebpush` in the worker image + set the three `FPLGURU_VAPID_*` env vars (`npx web-push generate-vapid-keys`).

**Verification (repo state after Task 7):** `python -m pytest -q -W error` → **146 passed**, no warnings; `ruff` clean; `alembic check` clean; web `vitest run` → 11 passed; `next build` → success (`/alerts` etc. prerender; `sw.js` + icons served from `public/`). **Merged to `main` as PR #8 (`b1febc8`).**

---

## P2h — Community Leaderboard (branch `feature/p2h-leaderboard`)

Plan: [`docs/plans/2026-08-27-p2h-community-leaderboard.md`](plans/2026-08-27-p2h-community-leaderboard.md). Executed inline, TDD per task. First Phase-2 sub-plan (unblocked — pure FPL-API data, depends only on P1a).

| Task | What | Status |
|---|---|---|
| 1 | `linked_team_leagues` + `league_standings` tables (`0008`) | ✅ |
| 2 | `FplClient.league_standings` + `normalize_entry` emits `leagues` + `normalize_league_standings` | ✅ |
| 3 | `sync_entry` pops `leagues` off `ent` (not a `LinkedTeam` col!) and upserts `linked_team_leagues` | ✅ |
| 4 | worker `_sync_league_standings` + task + `sync-league-standings` Beat (2h) | ✅ |
| 5 | `GET /entries/{id}/leagues` \| `/leagues/{id}/standings` \| `/leagues/{id}/search` \| `/entries/{id}/rank-history` | ✅ |
| 6+7 | web `getEntryLeagues`/`getLeagueStandings`/`searchLeague`/`getRankHistory` + `/leagues` + `/leagues/[id]` + `RankSparkline` + nav | ✅ |
| 8 | docs (README Leagues section, master plan ✅, this file) | 🔧 finishing |
See `git log feature/p2h-leaderboard` for exact SHAs.

**Model:** `_delta(rank, last) = last - rank` (positive = climbed). Mini-leagues come from the entry profile's `leagues.classic`; `sync_league_standings` fetches page 1 (top 50) of each distinct tracked league. Manager search is `ILIKE` over stored `league_standings` scoped to one league. Rank history is just `entry_gw_history.overall_rank` (already synced by P1a).

**Deviation from the plan:** the `normalize_entry` change (adds a `leagues` key) broke `sync_entry`'s `LinkedTeam(**ent, ...)` — Task 2's commit was briefly red for that reason; Task 3's `ent.pop("leagues", [])` fixed it. The branch HEAD is green; the intermediate commit is not (squash-merge, so it doesn't reach `main`).

**Verification (repo state after Task 7):** `python -m pytest -q -W error` → **156 passed**, no warnings; `ruff` clean; `alembic check` clean; web `vitest run` → 14 passed; `next build` → success (`/leagues` static, `/leagues/[id]` dynamic — fetches client-side). **Merged to `main` as PR #9 (`4a8f6ac`).**

---

## P2i — Free Tools Suite (branch `feature/p2i-free-tools`)

Plan: [`docs/plans/2026-08-27-p2i-free-tools.md`](plans/2026-08-27-p2i-free-tools.md). Executed inline, TDD per task.

| Task | What | Status |
|---|---|---|
| 1 | `players` gains `transfers_in_event` / `transfers_out_event` / `cost_change_event` / `form` (`0009`) + `normalize_players` | ✅ |
| 2 | `packages/tools` (`fplguru-tools`) — `trends`, `template_xi`, `template_diff`, `gw_calendar`, `pick_overpowered_xi` (pure; `_fill` picks the best formation by summed metric) | ✅ |
| 3 | `GET /trends` \| `/template` \| `/entries/{id}/template-diff` \| `/calendar?from_gw=&to_gw=` \| `/overpowered?horizon=` | ✅ |
| 4 | web `getTrends` / `getTemplate` / `getCalendar` / `getOverpowered` clients + types | ✅ |
| 5 | web `/tools` tabbed hub (Trends / Template / Calendar / Overpowered XI) + nav link | ✅ |
| 6 | docs (README Tools section, `.env.example` PitchAPI vars, master plan ✅ + P2a source recorded, this file) | 🔧 finishing |
See `git log feature/p2i-free-tools` for exact SHAs.

**Scope:** the master plan's fifth tool — **FDR/xG/CS Snapshot — is deferred to P2a** (PitchAPI xG ingestion). FDR alone already ships at `GET /fdr`. `pick_overpowered_xi` / `template_xi` ignore the £100m budget + max-3-per-club rule for now (documented follow-up). Formations tried: `_FORMATIONS` in `fplguru_tools` (3-4-3 … 5-3-2); the pick is whichever valid formation maximises the summed metric (ownership for template, xP for overpowered).

**Verification (repo state after Task 5):** `python -m pytest -q -W error` → **168 passed**, no warnings; `ruff` clean; `alembic check` clean; web `vitest run` → 17 passed; `next build` → success (`/tools` static).

---

## Milestone note (M2)

M2's "Stripe checkout works end-to-end in test mode" bullet is **void** (payments dropped in the
2026-08-27 scope pivot). The rest of M2 — `P1a, P1b, P1d, P1e, P1f, P1h` shipped + `P1c` Basic xP
serving predictions with a published backtest + installable PWA — **is met.** Phase 1 done.

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
- **Intermittent local full-suite flake** (seen from ~P2h on): a single worker DB test occasionally
  errors/fails with an asyncpg `DBAPIError` under the full `pytest -q` run (different test each time —
  `test_compute_xp`, `test_generate_alerts`), then passes in isolation and on a re-run. Root cause is
  the session-scoped event loop + many async DB tests sharing one engine. **CI (Linux) has been
  green on all 8 merged PRs.** Not yet chased down — candidate fix: function-scoped loop or an
  engine dispose between worker-task tests.
- `origin/main` is current through **PR #8 (`b1febc8`, Phase 1)** + **P2h** once its PR merges.
