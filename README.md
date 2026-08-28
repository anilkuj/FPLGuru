# FPLGuru

FPL (Fantasy Premier League) tracking + predictive-analytics platform.

This repo currently contains the **Foundation** layer: a monorepo with a resilient FPL→Postgres
data pipeline (Celery worker on a Beat schedule), a read-only FastAPI service, a Next.js PWA
shell, and a historical-data loader for future xP modelling.

- Build plan for what's here: [`docs/plans/2026-08-27-foundation.md`](docs/plans/2026-08-27-foundation.md)
- Roadmap for everything after: [`docs/plans/2026-08-27-fplguru-master-build-plan.md`](docs/plans/2026-08-27-fplguru-master-build-plan.md)
- Resuming mid-build: [`docs/RESUME-foundation.md`](docs/RESUME-foundation.md)

## Layout

```
packages/core         SQLAlchemy models, async DB session, settings, constants
packages/fpl_client    typed async client for the official FPL API (retry/backoff)
packages/ingest        pure fetch→row normalizers (FPL bootstrap/fixtures + historical CSV)
packages/ml            (stub — xP engine lands in a later sub-plan)
services/api           FastAPI: /health /ready /gameweeks /gameweeks/current /status
                       /link/{id} /entries/{id}[/history] /xp /players/{id}/xp /fdr
                       /gameweeks/current/live[/stream]
                       /entries/{id}/alerts /entries/{id}/alerts/seen
                       /entries/{id}/settings (GET + PATCH)
                       /push/vapid-public-key /entries/{id}/push/subscribe
services/worker        Celery worker + Beat: sync_bootstrap / sync_fixtures / sync_gw_stats
                       / compute_xp / sync_linked_teams / poll_live / generate_alerts
                       / deliver_push / sync_league_standings / sync_xg
apps/web               Next.js 16 (App Router) PWA shell
alembic/               async migrations
infra/                 docker-compose (Postgres 16 + Redis 7)
```

## Prerequisites

- **Python 3.12** from python.org — invoked as `py -3.12` (a bare `python` may resolve to the
  Windows Store stub until the venv is active; that's expected)
- **Node 22+** — `pnpm` comes via `corepack`
- **Docker Desktop**, running

> On this dev machine **Smart App Control is ON**, so the toolchain avoids unsigned native
> binaries: `venv`+`pip` (not `uv`), all tools invoked as `python -m <tool>`, `ruff` runs in
> CI only, and `numpy` is pinned `<2.5`.

## First run

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d --wait

py -3.12 -m venv .venv
# activate:  source .venv/Scripts/activate   (Git Bash)
#            .venv\Scripts\Activate.ps1       (PowerShell)
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

python -m alembic upgrade head

# populate the DB from the live FPL API
python -c "import asyncio; from fplguru_worker.tasks import sync_all; asyncio.run(sync_all())"
```

## Run

```bash
# API  →  http://localhost:8000
python -m uvicorn fplguru_api.main:app --reload --port 8000

# worker + scheduler (must be prefork or solo — not gevent/eventlet)
python -m celery -A fplguru_worker.app.celery_app worker -B --loglevel=info

# web  →  http://localhost:3000  (enter your FPL team ID on the home page)
pnpm --filter web dev
```

## Link a team

```bash
curl -XPOST localhost:8000/link/<FPL_TEAM_ID>     # your ID is in the FPL "Points" page URL
curl -s  localhost:8000/entries/<FPL_TEAM_ID>     # squad + per-player xP
curl -s  localhost:8000/entries/<FPL_TEAM_ID>/history
```
The worker's `sync_linked_teams` task re-syncs every linked team hourly.

## Test

```bash
python -m pytest -q          # needs Docker Postgres up; ruff runs in CI only
pnpm --filter web test
```

## xP model (Basic tier)

Transparent per-position ridge model (no scikit-learn), FPL-data-only leak-safe features
(rolling form, minutes reliability, home/away, price, opponent points-conceded-to-position).
Component breakdown and a non-linear model come with the Advanced tier (sub-plan P2b).

```bash
# one-time: pull historical data (gitignored)
python scripts/fetch_historical.py 2022-23 2023-24 2024-25

# train  ->  packages/ml/artifacts/basic/*.json   (small; committed)
python scripts/train_xp.py --csv data/historical/*_merged_gw.csv --out packages/ml/artifacts/basic

# walk-forward backtest  ->  docs/xp-backtest/<date>.md
python scripts/backtest_xp.py --csv data/historical/2024-25_merged_gw.csv

# serve: the worker's compute_xp task fills player_gw_predictions hourly.
#   GET /xp?horizon=5              -> all players, ranked by cumulative xP
#   GET /players/{id}/xp?horizon=5 -> per-gameweek breakdown + floor/ceiling
```

## Fixture difficulty (FDR)

Platform-computed FDR per team — FPL opponent strength tier blended with recent
goals-for / goals-against form, split into attack (`att_fdr`) and defence (`def_fdr`)
scores plus a 1–5 `band`. Horizon 1–10, available to everyone.

```bash
#   GET /fdr?horizon=5            -> every team, easiest fixtures first
#   GET /fdr?horizon=8&start_gw=12
```

xG-for/against and clean-sheet-probability columns arrive with the Advanced data tier (P2a).

## GW Live

While matches are in play, the worker's `poll_live` task (Beat cadence
`FPLGURU_LIVE_POLL_SECONDS`, default 60) pulls `event/{gw}/live`, projects provisional
3/2/1 bonus per fixture from BPS (standard-competition rank: BPS 30, 30, 25 → +3, +3, +1),
and upserts `player_gw_live`. The web `/live` page subscribes over SSE and falls back to a
15s poll if the stream errors.

```bash
#   GET /gameweeks/current/live         -> ranked live points + bonus projection + fixtures
#   GET /gameweeks/current/live/stream  -> text/event-stream; a fresh snapshot on each change
```

`poll_live` is a no-op (with an `ok` audit row) when no fixture is in play. Bonus is a live
projection until fixtures are final; finished-GW scoring is served from `player_gw_stats`
(the xP / actuals path), not this table.

## Alerts

A `generate_alerts` worker task (Beat, 30 min) builds a ranked, de-duplicated feed per
linked team: player availability changes (`status` / `chance_of_playing` / `news`),
blank/double gameweeks for teams you own, and **deadline reminders** at each
`linked_teams.reminder_offsets` minute mark before the next deadline (default
`[1440, 120, 60, 30]` = 24h / 2h / 1h / 30m; editable on the `/alerts` page or via
`PATCH /entries/{id}/settings`). The priority score is documented in
[`docs/design/2026-08-27-alert-priority-ranking.md`](docs/design/2026-08-27-alert-priority-ranking.md).
`linked_teams.alert_cap` (default `NULL` = uncapped) suppresses the lowest-priority alerts
beyond the cap — they stay stored, hidden unless you ask for them. Web Push delivery lands
with the PWA work (P1h); today the feed is in-app only.

```bash
#   GET   /entries/{id}/alerts[?include_suppressed=true]
#   POST  /entries/{id}/alerts/seen     {ids?: number[]}   # omit ids -> mark the visible feed
#   PATCH /entries/{id}/settings        {alert_cap: number | null}
```

`price_change` and `fdr_shift` generators need historical snapshots and are follow-ups.

## Leagues

`sync_entry` captures the manager's classic mini-leagues (`linked_team_leagues`), and a
`sync_league_standings` worker task (Beat, 2h) refreshes the top slice of each distinct tracked
league (`league_standings`). The "global" board is just the FPL "Overall" league (id 314) that
every manager is in; a dedicated global top-N crawl is a follow-up.

```bash
#   GET /entries/{id}/leagues                 -> mini-leagues + rank + weekly delta
#   GET /leagues/{id}/standings[?limit=50]    -> stored standings page
#   GET /leagues/{id}/search?q=               -> manager/team search within a league
#   GET /entries/{id}/rank-history            -> per-GW overall rank series
```

## Tools

Four analysis tools off the data already synced (the `players` table now also carries
`transfers_in_event` / `transfers_out_event` / `cost_change_event` / `form` from the bootstrap
sync):

```bash
#   GET /trends[?limit=10]              -> transfers in/out, price risers/fallers, most owned
#   GET /template                      -> the most-owned valid XI + combined ownership
#   GET /entries/{id}/template-diff    -> your squad vs the template (overlap + differentials)
#   GET /calendar?from_gw=&to_gw=      -> per-GW blank/double flags per team
#   GET /overpowered[?horizon=5]       -> best XI by cumulative Basic-xP over the horizon
```

The FDR/xG/CS Snapshot tool lands with **P2a** (PitchAPI xG ingestion) — FDR alone is already at
`GET /fdr`. `pick_overpowered_xi` / the template ignore the £100m budget + max-3-per-club for now.

## AI Captain

```bash
#   GET /entries/{id}/captain?horizon=3
```

Ranks captain picks two ways — **constrained** (your starting XI) and **unconstrained** (any
player) — by cumulative Basic xP over the horizon, and attaches a plain-English rationale from
**Google Gemini** (plain REST, no SDK). Each rationale is cached per `(player, gameweek)` in
`captain_rationale`; Gemini spend is tracked in `llm_calls` and calls are **skipped once
`FPLGURU_LLM_MONTHLY_USD_CAP` is reached for the calendar month**. With no `FPLGURU_GEMINI_KEY`
set, the endpoint still works and returns a templated summary (`rationale_source: "template"`).

## xG (PitchAPI)

`sync_xg` (Beat, daily) resolves finished fixtures to PitchAPI matches, maps ids
(`pitch_team_map` / `pitch_player_map` — auto surname+initial+team; fix misses with
`scripts/pitch_map.py`), and upserts `player_xg` (xG = summed shot `expected_goals`, plus xag /
minutes / key passes from the advanced-players endpoint).

```bash
#   GET /players/{id}/xg?last=6           -> recent per-GW xG/xA + totals
#   GET /xg-snapshot?last=6&position=MID  -> players ranked by xG+xA over the last N GWs
```

Blank `FPLGURU_PITCHAPI_KEY` → the task is a no-op. The response-shape assumptions come from the
published docs — run `python scripts/pitch_probe.py YYYY-MM-DD` to confirm them against a live
response before the first real sync. PitchAPI errors show up as a `pitch_xg` row on `/status`.

## PWA

The web app is installable (`manifest.json` + `public/sw.js`): the service worker precaches the
app shell and serves the last-known API response when offline. `PwaSetup` captures
`beforeinstallprompt` and shows an Install button.

A `deliver_push` worker task (Beat, 60s) sends each linked team's visible alert feed as **Web
Push** — but only when `FPLGURU_VAPID_PRIVATE_KEY` is set **and** `pywebpush` is importable.
`pywebpush` (which pulls `cryptography` / `aiohttp`) is **not** in `requirements-dev.txt` — it is
installed in the deploy image only (Smart App Control blocks those native binaries on the dev
box). With no key configured, `deliver_push` is a logged no-op and the in-app feed is unaffected.

```bash
#   GET    /push/vapid-public-key
#   POST   /entries/{id}/push/subscribe    {endpoint, keys: {p256dh, auth}}
#   DELETE /entries/{id}/push/subscribe    {endpoint}
# generate a VAPID keypair:  npx web-push generate-vapid-keys
```

Latest backtest: [`docs/xp-backtest/2026-08-27.md`](docs/xp-backtest/2026-08-27.md) — all four
position groups beat the naive-mean baseline.

## Data sources

- Official FPL API (`fantasy.premierleague.com/api/`) — live, no key, unofficial (no SLA)
- `vaastav/Fantasy-Premier-League` GitHub CSVs — historical per-GW data for backtesting;
  fetch with `python scripts/fetch_historical.py 2022-23 2023-24 2024-25`
