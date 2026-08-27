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
services/worker        Celery worker + Beat: sync_bootstrap / sync_fixtures
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

# web  →  http://localhost:3000
pnpm --filter web dev
```

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

Latest backtest: [`docs/xp-backtest/2026-08-27.md`](docs/xp-backtest/2026-08-27.md) — all four
position groups beat the naive-mean baseline.

## Data sources

- Official FPL API (`fantasy.premierleague.com/api/`) — live, no key, unofficial (no SLA)
- `vaastav/Fantasy-Premier-League` GitHub CSVs — historical per-GW data for backtesting;
  fetch with `python scripts/fetch_historical.py 2022-23 2023-24 2024-25`
