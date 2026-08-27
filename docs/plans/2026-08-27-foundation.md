# Foundation Implementation Plan (Repo/Infra + FPL Data Pipeline)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the FPLGuru monorepo and a resilient pipeline that keeps a Postgres database continuously in sync with the official FPL API (teams, players, fixtures, gameweeks), with sync-status tracking for graceful degradation, plus a minimal FastAPI service and Next.js PWA shell that read from it.

**Architecture:** A single root virtualenv with editable (`pip install -e`) installs of the Python packages (`core`, `fpl_client`, `ingest`, `ml`) and services (`api`, `worker`); pnpm workspace (via `corepack`) for `apps/web`. Ingest logic is pure (fetch → normalized rows) and DB-free so it's unit-testable against recorded fixtures; a Celery worker persists rows via Postgres `ON CONFLICT` upserts on a Beat schedule; FastAPI serves read-only endpoints; every sync writes a `data_sync_log` row so the UI can show "data as of X" and fall back to last-known state when the FPL API is down.

**Tech Stack:** Python 3.12 (python.org build), `venv` + `pip`, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic, Celery + Redis, httpx + tenacity, pytest + pytest-asyncio + respx, Next.js 15 + TypeScript + Tailwind + Vitest, Docker Compose (Postgres 16, Redis 7), GitHub Actions, pnpm (via corepack), ruff (CI-only).

> **Toolchain note — Smart App Control (SAC) is ON on the dev machine.** SAC blocks unsigned/unknown native binaries, so `uv` and standalone tool `.exe`s (`pytest.exe`, `ruff.exe`, …) are unusable locally. This plan therefore uses **`venv` + `pip`** and always invokes tools as **`python -m <tool>`** (`python -m pytest`, `python -m alembic`, `python -m uvicorn`, `python -m celery`). `ruff` runs **in CI only** (Linux runners, no SAC). If a native addon (`next`/`@next/swc`, `asyncpg` wheels) is ever SAC-blocked locally, run that piece in CI and note it — do not disable SAC.

**Reference:** Derived from `PRD.md` §6.1–6.3, §5.6, §7. Parent: [`2026-08-27-fplguru-master-build-plan.md`](2026-08-27-fplguru-master-build-plan.md).

---

## File Structure

**Created by this plan:**

| Path | Responsibility |
|---|---|
| `pyproject.toml` | root config only: `[tool.pytest.ini_options]` + `[tool.ruff]` (no project deps) |
| `requirements-dev.txt` | editable installs of all 6 local packages + test deps (pytest, pytest-asyncio, respx, httpx, asgi-lifespan, alembic) |
| `pnpm-workspace.yaml` | pnpm workspace declaring `apps/*` |
| `.env.example`, `.gitignore`, `README.md` | env template, ignores, run instructions |
| `infra/docker-compose.yml` | local Postgres 16 + Redis 7 |
| `packages/core/` | `settings.py` (pydantic-settings), `db.py` (async engine/session), `models.py` (SQLAlchemy models), `constants.py` |
| `alembic/`, `alembic.ini` | async migration env pointed at `core.models.Base.metadata` |
| `packages/fpl_client/` | `client.py` — typed async FPL API client with retry/backoff |
| `packages/ingest/` | `fpl.py` — normalize bootstrap-static + fixtures → row dicts; `historical.py` — normalize vaastav CSVs |
| `packages/ml/` | empty package stub (`__init__.py`) so the workspace member exists for later |
| `services/worker/` | `app.py` (Celery + Beat schedule), `tasks.py` (`sync_bootstrap`, `sync_fixtures`, `_upsert`) |
| `services/api/` | `main.py` — FastAPI app: `/health`, `/status`, `/gameweeks`, `/gameweeks/current` |
| `scripts/fetch_historical.py` | one-shot downloader for the vaastav historical dataset |
| `.github/workflows/ci.yml` | lint + tests on PR with Postgres/Redis service containers |
| `apps/web/` | minimal Next.js PWA shell: one page reading `/status`, `manifest.json` |

**Conventions:** Python packages use `src/` layout, hatchling build backend, import names `fplguru_core`, `fplguru_fpl_client`, `fplguru_ingest`, `fplguru_ml`. Tests live in each package's `tests/`. All datetimes are timezone-aware UTC.

---

## Task 1: Repo & package scaffold

**Files:**
- Create: `pyproject.toml`, `.gitattributes`, `requirements-dev.txt`, `pnpm-workspace.yaml`, `.env.example`
- Modify: `.gitignore` (already present from repo setup)
- Create: `packages/{core,fpl_client,ingest,ml}/src/<pkg>/__init__.py` + each `pyproject.toml`
- Create: `services/{api,worker}/src/<pkg>/__init__.py` + each `pyproject.toml`

> **Preconditions (already done during repo setup, verify only):** repo is a git repo, current branch is `feature/foundation`, `origin` = `https://github.com/anilkuj/FPLGuru.git`, `.gitignore` exists and contains `.venv/`, `.env`, `data/`, `node_modules/`. Python 3.12 from python.org is installed and reachable via **`py -3.12`** (the bare `python` command resolves to the Windows Store stub — that is expected; the venv provides a working `python` once activated). A separate Python 3.14 may also be present — ignore it, always pin `py -3.12`.

- [ ] **Step 1: Verify preconditions**

Run:
```bash
git branch --show-current && py -3.12 --version && cat .gitignore
```
Expected: `feature/foundation`, `Python 3.12.x`, `.gitignore` listing `.venv/` `.env` `data/` etc. If `py -3.12` fails or reports a different version, STOP and report BLOCKED.

- [ ] **Step 2: Ensure `.gitignore` covers Python venv + build**

`.gitignore` must contain (append any missing lines):
```gitignore
__pycache__/
*.pyc
.venv/
.env
.pytest_cache/
.ruff_cache/
node_modules/
apps/web/.next/
dist/
*.egg-info/
.coverage
data/
```

- [ ] **Step 3: Write root `pyproject.toml` (config only — no deps, no uv) and `.gitattributes`**

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
testpaths = ["packages", "services"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

`asyncio_default_fixture_loop_scope = "session"` is required by pytest-asyncio 1.x so Task 4's session-scoped async `_engine` fixture shares one event loop with the function-scoped tests that use it.

`.gitattributes` (repo has `core.autocrlf=true`; without this, fresh clones check out CRLF and break Linux/Docker text files + Task 6's byte-exact JSON fixtures):
```gitattributes
* text=auto eol=lf
*.png binary
*.ico binary
```

- [ ] **Step 4: Write `requirements-dev.txt` (leaf-first editable installs + test deps)**

```text
-e ./packages/core
-e ./packages/fpl_client
-e ./packages/ingest
-e ./packages/ml
-e ./services/api
-e ./services/worker

pytest>=8.2
pytest-asyncio>=1.0,<2
respx>=0.21
httpx>=0.27
asgi-lifespan>=2.1
alembic>=1.13
```

Order matters: `core` is installed before the packages that depend on it, so pip resolves the `fplguru-core` requirement to the local editable project rather than PyPI. `ruff` is intentionally absent — it runs in CI only (see the Toolchain note at the top).

- [ ] **Step 5: Write `pnpm-workspace.yaml`**

```yaml
packages:
  - "apps/*"
```

- [ ] **Step 6: Create each Python package/service skeleton**

For each of `packages/core`, `packages/fpl_client`, `packages/ingest`, `packages/ml`, `services/api`, `services/worker`: create `src/<import_name>/__init__.py` (empty) and `pyproject.toml`. Template (substitute name/import_name per package — deps start as `[]`, filled in by later tasks):

```toml
[project]
name = "fplguru-core"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/fplguru_core"]
```

Import-name map: core→`fplguru_core`, fpl_client→`fplguru_fpl_client`, ingest→`fplguru_ingest`, ml→`fplguru_ml`, api→`fplguru_api`, worker→`fplguru_worker`.

- [ ] **Step 7: Create the virtualenv and install everything editable**

Run (from repo root):
```bash
py -3.12 -m venv .venv
```
Then activate it — **Git Bash:** `source .venv/Scripts/activate` · **PowerShell:** `.venv\Scripts\Activate.ps1` · **cmd:** `.venv\Scripts\activate.bat`. Confirm `python -c "import sys; print(sys.version)"` reports 3.12.x from inside `.venv`. Then:
```bash
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```
Expected: all 6 local packages install in editable mode, test deps resolve, exit 0. Every later `python -m ...` command in this plan assumes this venv is active.

- [ ] **Step 8: Add a trivial import test**

Create `packages/core/tests/test_smoke.py`:
```python
def test_package_imports():
    import fplguru_core  # noqa: F401
```

Run:
```bash
python -m pytest packages/core/tests/test_smoke.py -v
```
Expected: 1 passed.

- [ ] **Step 9: Commit**

```bash
git add -A -- ':!docs'
git commit -m "chore: scaffold pip/pnpm monorepo (venv + editable installs)"
```

---

## Task 2: Local infra + settings module

**Files:**
- Create: `infra/docker-compose.yml`
- Create: `packages/core/src/fplguru_core/settings.py`
- Test: `packages/core/tests/test_settings.py`
- Modify: `packages/core/pyproject.toml` (add `pydantic-settings`)
- Create: `.env.example`

- [ ] **Step 1: Write `infra/docker-compose.yml`**

```yaml
name: fplguru

services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: fplguru
      POSTGRES_PASSWORD: fplguru
      POSTGRES_DB: fplguru
    ports: ["5432:5432"]
    volumes: ["fplguru_pg:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U fplguru -d fplguru"]
      interval: 2s
      timeout: 3s
      retries: 20
  redis:
    image: redis:7
    ports: ["6379:6379"]
volumes:
  fplguru_pg:
```

The `postgres` healthcheck lets Task 4 use `up -d --wait` so `alembic` doesn't race the server's startup. `name: fplguru` keeps container/volume names stable regardless of the compose file's directory.

- [ ] **Step 2: Add dependency**

In `packages/core/pyproject.toml` set `dependencies = ["pydantic-settings>=2.3,<3", "pydantic>=2.7,<3"]` (upper bounds so a future pydantic 3 can't silently shift the whole stack), then run `pip install -r requirements-dev.txt`.

- [ ] **Step 3: Write the failing test**

`packages/core/tests/test_settings.py`:
```python
from fplguru_core.settings import Settings


def test_defaults_point_at_local_infra(monkeypatch):
    for key in (
        "FPLGURU_DATABASE_URL", "FPLGURU_REDIS_URL",
        "FPLGURU_FPL_API_BASE", "FPLGURU_ENVIRONMENT",
    ):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.database_url.startswith("postgresql+asyncpg://")
    assert s.redis_url.startswith("redis://")
    assert s.fpl_api_base == "https://fantasy.premierleague.com/api"


def test_env_prefix_override(monkeypatch):
    monkeypatch.setenv("FPLGURU_ENVIRONMENT", "ci")
    assert Settings(_env_file=None).environment == "ci"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest packages/core/tests/test_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: fplguru_core.settings`.

- [ ] **Step 5: Write `settings.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="FPLGURU_", extra="ignore"
    )

    database_url: str = "postgresql+asyncpg://fplguru:fplguru@localhost:5432/fplguru"
    redis_url: str = "redis://localhost:6379/0"
    fpl_api_base: str = "https://fantasy.premierleague.com/api"
    environment: str = "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest packages/core/tests/test_settings.py -v`
Expected: 2 passed.

- [ ] **Step 7: Write `.env.example`** (already created in Task 1 — ensure it has all four keys)

```dotenv
FPLGURU_DATABASE_URL=postgresql+asyncpg://fplguru:fplguru@localhost:5432/fplguru
FPLGURU_REDIS_URL=redis://localhost:6379/0
FPLGURU_FPL_API_BASE=https://fantasy.premierleague.com/api
FPLGURU_ENVIRONMENT=local
```

- [ ] **Step 8: Start infra and commit**

Run:
```bash
docker compose -f infra/docker-compose.yml up -d --wait
```
Expected: exits 0 once healthy; `docker compose -f infra/docker-compose.yml ps` shows `postgres` as `Up (healthy)` and `redis` as `Up`.

```bash
git add -A -- ':!docs'
git commit -m "feat: local docker-compose infra and core settings"
```

> Run `python -m pytest` from the **repo root** — `Settings.model_config` resolves `env_file=".env"` relative to CWD, so a stray `.env` elsewhere (or none) changes results.

---

## Task 3: Core DB models & session

**Files:**
- Create: `packages/core/src/fplguru_core/constants.py`
- Create: `packages/core/src/fplguru_core/db.py`
- Create: `packages/core/src/fplguru_core/models.py`
- Test: `packages/core/tests/test_models.py`
- Modify: `packages/core/pyproject.toml` (add `sqlalchemy[asyncio]`, `asyncpg`, `greenlet`)

- [ ] **Step 1: Add dependencies**

Set `packages/core/pyproject.toml` `dependencies` to:
```toml
dependencies = [
    "pydantic>=2.7,<3",
    "pydantic-settings>=2.3,<3",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30",
    "greenlet>=3.0",
]
```
Run `pip install -r requirements-dev.txt`. (`sqlalchemy>=2.0.36` / `asyncpg>=0.30` are the first releases with wheels/support current on Python 3.12–3.13; keep them recent.)

- [ ] **Step 2: Write `constants.py`**

```python
# FPL bootstrap-static element_types map to these position codes.
POSITION_BY_ELEMENT_TYPE: dict[int, str] = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
```

- [ ] **Step 3: Write `db.py`**

`get_engine` / `get_sessionmaker` are cached so production doesn't rebuild the pool per request. Because they read `get_settings()` (itself cached) at first call, a test that changes the DB URL must reset **all three** caches — so `db.py` exposes one `reset_state()` that does exactly that. Task 4's root `conftest.py` calls it via an autouse fixture; no test should hand-roll `get_settings.cache_clear()`.

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fplguru_core.settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Imperative session helper for scripts / one-off tasks.

    Does NOT commit — call ``await session.commit()`` yourself. On exit the
    session is closed (rolled back if not committed).
    """
    async with get_sessionmaker()() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose the cached engine's pool. Call from FastAPI lifespan shutdown."""
    if get_engine.cache_info().currsize:
        await get_engine().dispose()


def reset_state() -> None:
    """Clear cached settings/engine/sessionmaker. For tests only.

    Does not dispose the dropped engine's pool; acceptable for tests.
    """
    get_sessionmaker.cache_clear()
    get_engine.cache_clear()
    get_settings.cache_clear()
```

- [ ] **Step 4: Write the failing test**

`packages/core/tests/test_models.py`:
```python
from fplguru_core.models import Base, DataSyncLog, Fixture, Gameweek, Player, Team


def test_expected_tables_registered():
    assert set(Base.metadata.tables) == {
        "teams", "gameweeks", "players", "fixtures", "data_sync_log",
    }


def test_player_has_availability_columns():
    cols = {c.name for c in Player.__table__.columns}
    assert {"status", "chance_of_playing_next_round", "news", "position", "team_id"} <= cols


def test_fixture_gameweek_is_nullable_for_unscheduled():
    assert Fixture.__table__.c.gameweek_id.nullable is True
```

- [ ] **Step 5: Run test to verify it fails**

Run: `python -m pytest packages/core/tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: fplguru_core.models`.

- [ ] **Step 6: Write `models.py`**

```python
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, MetaData, String, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    # Deterministic constraint names so migrations aren't tied to Postgres defaults.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referent_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class _TimestampMixin:
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Team(_TimestampMixin, Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # FPL team id
    name: Mapped[str] = mapped_column(String(64))
    short_name: Mapped[str] = mapped_column(String(8))
    strength_overall_home: Mapped[int] = mapped_column(Integer, default=0)
    strength_overall_away: Mapped[int] = mapped_column(Integer, default=0)
    strength_attack_home: Mapped[int] = mapped_column(Integer, default=0)
    strength_attack_away: Mapped[int] = mapped_column(Integer, default=0)
    strength_defence_home: Mapped[int] = mapped_column(Integer, default=0)
    strength_defence_away: Mapped[int] = mapped_column(Integer, default=0)


class Gameweek(_TimestampMixin, Base):
    __tablename__ = "gameweeks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # event id 1..38
    name: Mapped[str] = mapped_column(String(32))
    deadline_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    is_next: Mapped[bool] = mapped_column(Boolean, default=False)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    average_entry_score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Player(_TimestampMixin, Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # FPL element id
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    first_name: Mapped[str] = mapped_column(String(64))
    second_name: Mapped[str] = mapped_column(String(64))
    web_name: Mapped[str] = mapped_column(String(64))
    position: Mapped[str] = mapped_column(String(3))  # GK/DEF/MID/FWD
    now_cost: Mapped[int] = mapped_column(Integer)  # tenths of a million
    status: Mapped[str] = mapped_column(String(1))  # a/d/i/s/u/n
    chance_of_playing_next_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    news: Mapped[str] = mapped_column(String, default="", server_default="")
    selected_by_percent: Mapped[float] = mapped_column(Float, default=0.0)
    total_points: Mapped[int] = mapped_column(Integer, default=0)


class Fixture(_TimestampMixin, Base):
    __tablename__ = "fixtures"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # FPL fixture id
    gameweek_id: Mapped[int | None] = mapped_column(
        ForeignKey("gameweeks.id"), nullable=True
    )  # null = not yet scheduled to a GW
    kickoff_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    home_difficulty: Mapped[int] = mapped_column(Integer)
    away_difficulty: Mapped[int] = mapped_column(Integer)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DataSyncLog(Base):
    __tablename__ = "data_sync_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), index=True)  # fpl_bootstrap | fpl_fixtures
    status: Mapped[str] = mapped_column(String(16))  # ok | error
    detail: Mapped[str] = mapped_column(String, default="", server_default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest packages/core/tests/test_models.py -v`
Expected: 3 passed.

- [ ] **Step 8: Commit**

```bash
git add -A -- ':!docs'
git commit -m "feat: core SQLAlchemy models and async session"
```

---

## Task 4: Alembic migrations + DB test harness

**Files:**
- Create: `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_initial.py`
- Create: `packages/core/tests/conftest.py` (shared DB fixture for all packages via root `conftest.py`)
- Create: `conftest.py` (repo root — re-exports the db fixtures)

- [ ] **Step 1: Init the async Alembic template**

`alembic>=1.13` is already in `requirements-dev.txt` (installed in Task 1). From the repo root with the venv active:
```bash
python -m alembic init -t async alembic
```
Expected: creates `alembic/`, `alembic.ini`.

- [ ] **Step 2: Point `alembic/env.py` at core metadata + settings**

Replace the generated `target_metadata = None` and URL handling so `env.py` contains:
```python
from fplguru_core.models import Base
from fplguru_core.settings import get_settings

target_metadata = Base.metadata

def _url() -> str:
    return get_settings().database_url
```
and every `config.get_main_option("sqlalchemy.url")` call is replaced with `_url()`. Leave the rest of the async template intact.

- [ ] **Step 3: Autogenerate the initial migration**

Bring infra up and wait for health, then reset the `public` schema of the `fplguru` DB so autogenerate diffs against an empty database (a stale/persisted volume would make it emit an empty migration):
```bash
docker compose -f infra/docker-compose.yml up -d --wait
docker compose -f infra/docker-compose.yml exec -T postgres \
  psql -U fplguru -d fplguru -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
python -m alembic revision --autogenerate -m "initial" --rev-id 0001
```
Expected: creates `alembic/versions/0001_initial.py` whose `upgrade()` has `op.create_table(...)` for all 5 tables (`teams`, `gameweeks`, `players`, `fixtures`, `data_sync_log`). If `upgrade()` is empty or `pass`, the schema wasn't clean — re-run the `DROP SCHEMA` line and regenerate.

- [ ] **Step 4: Apply and verify**

Run:
```bash
python -m alembic upgrade head
```
Expected: `Running upgrade  -> 0001, initial`. Verify:
```bash
docker compose -f infra/docker-compose.yml exec -T postgres psql -U fplguru -d fplguru -c "\dt"
```
Expected: lists `teams, gameweeks, players, fixtures, data_sync_log, alembic_version`.

- [ ] **Step 5: Write the shared DB test fixtures**

`conftest.py` (repo root). Tests run against a dedicated `fplguru_test` database (never the dev `fplguru` DB). The autouse `_point_app_at_test_db` fixture sets `FPLGURU_DATABASE_URL` to the test DB and calls `db.reset_state()`, so any app code under test that calls `get_settings()` / `get_sessionmaker()` (Tasks 7, 10) transparently hits `fplguru_test` — no per-test monkeypatching of `get_sessionmaker` needed.

```python
import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fplguru_core import db as _db
from fplguru_core.models import Base

TEST_DB_URL = os.environ.get(
    "FPLGURU_TEST_DATABASE_URL",
    "postgresql+asyncpg://fplguru:fplguru@localhost:5432/fplguru_test",
)


@pytest_asyncio.fixture(scope="session")
async def _engine():
    # create the test database if it doesn't exist yet
    admin_url = TEST_DB_URL.rsplit("/", 1)[0] + "/postgres"
    dbname = TEST_DB_URL.rsplit("/", 1)[1]
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        exists = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": dbname}
        )
        if exists.first() is None:
            await conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    await admin.dispose()

    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
def _point_app_at_test_db(monkeypatch):
    monkeypatch.setenv("FPLGURU_DATABASE_URL", TEST_DB_URL)
    _db.reset_state()
    yield
    _db.reset_state()


@pytest_asyncio.fixture
async def db_session(_engine):
    maker = async_sessionmaker(_engine, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(_engine):
    yield
    async with _engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(
                text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE')
            )
```

> The `Files` list mentions `packages/core/tests/conftest.py` — not needed; the repo-root `conftest.py` is discovered by pytest for every package. Create only the root one.

- [ ] **Step 6: Prove the fixture works**

`packages/core/tests/test_db_fixture.py`:
```python
from sqlalchemy import select

from fplguru_core.models import Team


async def test_can_insert_and_read(db_session):
    db_session.add(Team(id=1, name="Arsenal", short_name="ARS"))
    await db_session.commit()
    got = (await db_session.execute(select(Team).where(Team.id == 1))).scalar_one()
    assert got.short_name == "ARS"
```

Run: `python -m pytest packages/core/tests/test_db_fixture.py -v`
Expected: 1 passed (test DB `fplguru_test` auto-created).

- [ ] **Step 7: Commit**

```bash
git add -A -- ':!docs'
git commit -m "feat: alembic async migrations and pytest postgres fixtures"
```

---

## Task 5: FPL API client

**Files:**
- Create: `packages/fpl_client/src/fplguru_fpl_client/__init__.py` (re-export), `client.py`
- Test: `packages/fpl_client/tests/test_client.py`
- Modify: `packages/fpl_client/pyproject.toml` (deps: `httpx>=0.27`, `tenacity>=8.3`)

- [ ] **Step 1: Add dependencies**

Set `packages/fpl_client/pyproject.toml` `dependencies = ["httpx>=0.27", "tenacity>=8.3"]`, `pip install -r requirements-dev.txt`.

- [ ] **Step 2: Write the failing test**

`packages/fpl_client/tests/test_client.py`:
```python
import httpx
import pytest
import respx

from fplguru_fpl_client import FplApiError, FplClient

BASE = "https://fpl.test/api"


@respx.mock
async def test_bootstrap_static_returns_json():
    respx.get(f"{BASE}/bootstrap-static/").mock(
        return_value=httpx.Response(200, json={"teams": [], "elements": [], "events": []})
    )
    client = FplClient(BASE)
    data = await client.bootstrap_static()
    await client.aclose()
    assert data == {"teams": [], "elements": [], "events": []}


@respx.mock
async def test_fixtures_returns_list():
    respx.get(f"{BASE}/fixtures/").mock(return_value=httpx.Response(200, json=[{"id": 1}]))
    client = FplClient(BASE)
    assert await client.fixtures() == [{"id": 1}]
    await client.aclose()


@respx.mock
async def test_retries_on_5xx_then_succeeds():
    route = respx.get(f"{BASE}/fixtures/")
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, json=[{"id": 9}]),
    ]
    client = FplClient(BASE)
    assert await client.fixtures() == [{"id": 9}]
    await client.aclose()
    assert route.call_count == 3


@respx.mock
async def test_raises_after_exhausting_retries():
    respx.get(f"{BASE}/fixtures/").mock(return_value=httpx.Response(503))
    client = FplClient(BASE)
    with pytest.raises(FplApiError):
        await client.fixtures()
    await client.aclose()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest packages/fpl_client/tests/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError: fplguru_fpl_client`.

- [ ] **Step 4: Write `client.py`**

```python
from typing import Any

import httpx
from tenacity import (
    retry, retry_if_exception_type, stop_after_attempt, wait_exponential,
)


class FplApiError(Exception):
    pass


class FplClient:
    def __init__(self, base_url: str, http: httpx.AsyncClient | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(
            timeout=15.0, headers={"User-Agent": "FPLGuru/0.1 (+https://fplguru.app)"}
        )
        self._owns_http = http is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, max=8),
        retry=retry_if_exception_type((httpx.TransportError, FplApiError)),
        reraise=True,
    )
    async def _get(self, path: str) -> Any:
        try:
            resp = await self._http.get(f"{self._base}/{path}")
        except httpx.TransportError:
            raise
        if resp.status_code >= 500:
            raise FplApiError(f"GET {path} -> {resp.status_code}")
        resp.raise_for_status()
        return resp.json()

    async def bootstrap_static(self) -> dict:
        return await self._get("bootstrap-static/")

    async def fixtures(self) -> list:
        return await self._get("fixtures/")
```

`packages/fpl_client/src/fplguru_fpl_client/__init__.py`:
```python
from fplguru_fpl_client.client import FplApiError, FplClient

__all__ = ["FplApiError", "FplClient"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest packages/fpl_client/tests/test_client.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add -A -- ':!docs'
git commit -m "feat: resilient async FPL API client with retry/backoff"
```

---

## Task 6: Ingest normalizers (bootstrap-static + fixtures)

**Files:**
- Create: `packages/ingest/src/fplguru_ingest/fpl.py`
- Create: `packages/ingest/tests/fixtures/bootstrap_sample.json`, `fixtures_sample.json`
- Test: `packages/ingest/tests/test_fpl_normalizers.py`
- Modify: `packages/ingest/pyproject.toml` (dep: `fplguru-core` workspace)

- [ ] **Step 1: Add dependency**

Set `packages/ingest/pyproject.toml` `dependencies = ["fplguru-core"]`, `pip install -r requirements-dev.txt`.

- [ ] **Step 2: Create trimmed fixture files**

`packages/ingest/tests/fixtures/bootstrap_sample.json` — one team, one player, two events (real FPL shape, trimmed to fields the normalizers read):
```json
{
  "teams": [
    {"id": 1, "name": "Arsenal", "short_name": "ARS",
     "strength_overall_home": 1300, "strength_overall_away": 1310,
     "strength_attack_home": 1350, "strength_attack_away": 1340,
     "strength_defence_home": 1250, "strength_defence_away": 1260}
  ],
  "events": [
    {"id": 1, "name": "Gameweek 1", "deadline_time": "2025-08-15T17:30:00Z",
     "is_current": false, "is_next": true, "finished": false, "average_entry_score": null},
    {"id": 2, "name": "Gameweek 2", "deadline_time": "2025-08-22T17:30:00Z",
     "is_current": false, "is_next": false, "finished": false, "average_entry_score": null}
  ],
  "elements": [
    {"id": 11, "team": 1, "element_type": 3, "first_name": "Bukayo", "second_name": "Saka",
     "web_name": "Saka", "now_cost": 100, "status": "a",
     "chance_of_playing_next_round": 100, "news": "",
     "selected_by_percent": "42.1", "total_points": 0}
  ]
}
```

`packages/ingest/tests/fixtures/fixtures_sample.json`:
```json
[
  {"id": 1, "event": 1, "kickoff_time": "2025-08-16T14:00:00Z",
   "team_h": 1, "team_a": 1, "team_h_difficulty": 3, "team_a_difficulty": 2,
   "finished": false, "team_h_score": null, "team_a_score": null},
  {"id": 2, "event": null, "kickoff_time": null,
   "team_h": 1, "team_a": 1, "team_h_difficulty": 4, "team_a_difficulty": 4,
   "finished": false, "team_h_score": null, "team_a_score": null}
]
```

- [ ] **Step 3: Write the failing test**

`packages/ingest/tests/test_fpl_normalizers.py`:
```python
import json
from pathlib import Path

from fplguru_ingest.fpl import (
    normalize_fixtures, normalize_gameweeks, normalize_players, normalize_teams,
)

FIX = Path(__file__).parent / "fixtures"
BOOTSTRAP = json.loads((FIX / "bootstrap_sample.json").read_text())
FIXTURES = json.loads((FIX / "fixtures_sample.json").read_text())


def test_normalize_teams():
    rows = normalize_teams(BOOTSTRAP)
    assert rows == [{
        "id": 1, "name": "Arsenal", "short_name": "ARS",
        "strength_overall_home": 1300, "strength_overall_away": 1310,
        "strength_attack_home": 1350, "strength_attack_away": 1340,
        "strength_defence_home": 1250, "strength_defence_away": 1260,
    }]


def test_normalize_gameweeks_parses_utc_deadline():
    rows = normalize_gameweeks(BOOTSTRAP)
    assert rows[0]["id"] == 1
    assert rows[0]["deadline_time"].tzinfo is not None
    assert rows[0]["deadline_time"].isoformat() == "2025-08-15T17:30:00+00:00"
    assert rows[0]["is_next"] is True


def test_normalize_players_maps_position_and_percent():
    row = normalize_players(BOOTSTRAP)[0]
    assert row["position"] == "MID"
    assert row["team_id"] == 1
    assert row["selected_by_percent"] == 42.1
    assert row["now_cost"] == 100


def test_normalize_fixtures_handles_null_event_and_kickoff():
    rows = normalize_fixtures(FIXTURES)
    assert rows[0]["gameweek_id"] == 1
    assert rows[0]["kickoff_time"].isoformat() == "2025-08-16T14:00:00+00:00"
    assert rows[1]["gameweek_id"] is None
    assert rows[1]["kickoff_time"] is None
    assert rows[1]["home_difficulty"] == 4
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest packages/ingest/tests/test_fpl_normalizers.py -v`
Expected: FAIL — `ModuleNotFoundError: fplguru_ingest.fpl`.

- [ ] **Step 5: Write `fpl.py`**

```python
from datetime import datetime
from typing import Any

from fplguru_core.constants import POSITION_BY_ELEMENT_TYPE


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_teams(bootstrap: dict[str, Any]) -> list[dict]:
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "short_name": t["short_name"],
            "strength_overall_home": t["strength_overall_home"],
            "strength_overall_away": t["strength_overall_away"],
            "strength_attack_home": t["strength_attack_home"],
            "strength_attack_away": t["strength_attack_away"],
            "strength_defence_home": t["strength_defence_home"],
            "strength_defence_away": t["strength_defence_away"],
        }
        for t in bootstrap["teams"]
    ]


def normalize_gameweeks(bootstrap: dict[str, Any]) -> list[dict]:
    return [
        {
            "id": e["id"],
            "name": e["name"],
            "deadline_time": _parse_dt(e["deadline_time"]),
            "is_current": bool(e["is_current"]),
            "is_next": bool(e["is_next"]),
            "finished": bool(e["finished"]),
            "average_entry_score": e.get("average_entry_score"),
        }
        for e in bootstrap["events"]
    ]


def normalize_players(bootstrap: dict[str, Any]) -> list[dict]:
    return [
        {
            "id": el["id"],
            "team_id": el["team"],
            "first_name": el["first_name"],
            "second_name": el["second_name"],
            "web_name": el["web_name"],
            "position": POSITION_BY_ELEMENT_TYPE[el["element_type"]],
            "now_cost": el["now_cost"],
            "status": el["status"],
            "chance_of_playing_next_round": el.get("chance_of_playing_next_round"),
            "news": el.get("news", ""),
            "selected_by_percent": float(el["selected_by_percent"]),
            "total_points": el["total_points"],
        }
        for el in bootstrap["elements"]
    ]


def normalize_fixtures(fixtures: list[dict[str, Any]]) -> list[dict]:
    return [
        {
            "id": f["id"],
            "gameweek_id": f["event"],
            "kickoff_time": _parse_dt(f.get("kickoff_time")),
            "home_team_id": f["team_h"],
            "away_team_id": f["team_a"],
            "home_difficulty": f["team_h_difficulty"],
            "away_difficulty": f["team_a_difficulty"],
            "finished": bool(f["finished"]),
            "home_score": f.get("team_h_score"),
            "away_score": f.get("team_a_score"),
        }
        for f in fixtures
    ]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest packages/ingest/tests/test_fpl_normalizers.py -v`
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add -A -- ':!docs'
git commit -m "feat: pure FPL bootstrap/fixtures normalizers with fixtures"
```

---

## Task 7: Celery worker + `sync_bootstrap` task

**Files:**
- Create: `services/worker/src/fplguru_worker/app.py`, `tasks.py`
- Test: `services/worker/tests/test_sync_bootstrap.py`
- Modify: `services/worker/pyproject.toml` (deps: `celery[redis]>=5.4`, `fplguru-core`, `fplguru-fpl-client`, `fplguru-ingest`)

- [ ] **Step 1: Add dependencies**

Set `services/worker/pyproject.toml`:
```toml
dependencies = [
    "celery[redis]>=5.4",
    "fplguru-core",
    "fplguru-fpl-client",
    "fplguru-ingest",
]
```
Run `pip install -r requirements-dev.txt`.

- [ ] **Step 2: Write `app.py`**

```python
from celery import Celery

from fplguru_core.settings import get_settings

settings = get_settings()

celery_app = Celery("fplguru", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    timezone="UTC",
    task_track_started=True,
    task_acks_late=True,
    beat_schedule={
        "sync-bootstrap": {"task": "sync_bootstrap", "schedule": 900.0},   # every 15 min
        "sync-fixtures": {"task": "sync_fixtures", "schedule": 3600.0},    # hourly
    },
)

from fplguru_worker import tasks  # noqa: E402,F401  (register tasks)
```

- [ ] **Step 3: Write the failing test**

`services/worker/tests/test_sync_bootstrap.py`:
```python
import json
from pathlib import Path

import httpx
import respx
from sqlalchemy import func, select

from fplguru_core.models import DataSyncLog, Gameweek, Player, Team
from fplguru_worker.tasks import _sync_bootstrap

BOOTSTRAP = json.loads(
    (Path(__file__).parents[3] / "packages/ingest/tests/fixtures/bootstrap_sample.json").read_text()
)
BASE = "https://fpl.test/api"


@respx.mock
async def test_sync_bootstrap_upserts_and_logs(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    from fplguru_core.settings import get_settings
    get_settings.cache_clear()
    respx.get(f"{BASE}/bootstrap-static/").mock(return_value=httpx.Response(200, json=BOOTSTRAP))

    await _sync_bootstrap()

    assert (await db_session.execute(select(func.count()).select_from(Team))).scalar() == 1
    assert (await db_session.execute(select(func.count()).select_from(Gameweek))).scalar() == 2
    assert (await db_session.execute(select(func.count()).select_from(Player))).scalar() == 1
    log = (await db_session.execute(select(DataSyncLog))).scalar_one()
    assert (log.source, log.status) == ("fpl_bootstrap", "ok")


@respx.mock
async def test_sync_bootstrap_is_idempotent(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    from fplguru_core.settings import get_settings
    get_settings.cache_clear()
    respx.get(f"{BASE}/bootstrap-static/").mock(return_value=httpx.Response(200, json=BOOTSTRAP))

    await _sync_bootstrap()
    await _sync_bootstrap()

    assert (await db_session.execute(select(func.count()).select_from(Player))).scalar() == 1
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest services/worker/tests/test_sync_bootstrap.py -v`
Expected: FAIL — `ImportError: cannot import name '_sync_bootstrap'`.

- [ ] **Step 5: Write `tasks.py`**

```python
import asyncio
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from fplguru_core.db import get_sessionmaker
from fplguru_core.models import DataSyncLog, Fixture, Gameweek, Player, Team
from fplguru_core.settings import get_settings
from fplguru_fpl_client import FplClient
from fplguru_ingest.fpl import (
    normalize_fixtures, normalize_gameweeks, normalize_players, normalize_teams,
)
from fplguru_worker.app import celery_app


async def _upsert(session, model, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(model).values(rows)
    update_cols = {
        c.name: stmt.excluded[c.name]
        for c in model.__table__.columns
        if c.name not in ("id",)
    }
    if "updated_at" in model.__table__.columns:
        update_cols["updated_at"] = func.now()
    stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols)
    await session.execute(stmt)


async def _record(session, source: str, status: str, started: datetime, detail: str = "") -> None:
    session.add(
        DataSyncLog(
            source=source, status=status, detail=detail,
            started_at=started, finished_at=datetime.now(UTC),
        )
    )


async def _sync_bootstrap() -> None:
    started = datetime.now(UTC)
    client = FplClient(get_settings().fpl_api_base)
    try:
        data = await client.bootstrap_static()
    finally:
        await client.aclose()
    maker = get_sessionmaker()
    async with maker() as session:
        try:
            async with session.begin():
                await _upsert(session, Team, normalize_teams(data))
                await _upsert(session, Gameweek, normalize_gameweeks(data))
                await _upsert(session, Player, normalize_players(data))
                await _record(session, "fpl_bootstrap", "ok", started)
        except Exception as exc:  # noqa: BLE001
            async with session.begin():
                await _record(session, "fpl_bootstrap", "error", started, str(exc)[:500])
            raise


async def _sync_fixtures() -> None:
    started = datetime.now(UTC)
    client = FplClient(get_settings().fpl_api_base)
    try:
        data = await client.fixtures()
    finally:
        await client.aclose()
    maker = get_sessionmaker()
    async with maker() as session:
        try:
            async with session.begin():
                await _upsert(session, Fixture, normalize_fixtures(data))
                await _record(session, "fpl_fixtures", "ok", started)
        except Exception as exc:  # noqa: BLE001
            async with session.begin():
                await _record(session, "fpl_fixtures", "error", started, str(exc)[:500])
            raise


@celery_app.task(name="sync_bootstrap", bind=True, max_retries=3, default_retry_delay=60)
def sync_bootstrap(self) -> None:
    try:
        asyncio.run(_sync_bootstrap())
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc)


@celery_app.task(name="sync_fixtures", bind=True, max_retries=3, default_retry_delay=60)
def sync_fixtures(self) -> None:
    try:
        asyncio.run(_sync_fixtures())
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc)
```

> **DB-URL note for tests:** the root `conftest.py` fixtures create/populate `fplguru_test`, but `_sync_bootstrap` uses `get_sessionmaker()` which reads `FPLGURU_DATABASE_URL`. In `services/worker/tests/conftest.py` add an autouse fixture that points the app sessionmaker at the test DB:
> ```python
> import pytest
> from fplguru_core import db
> from fplguru_core.settings import get_settings
>
> @pytest.fixture(autouse=True)
> def _use_test_db(_engine, monkeypatch):
>     monkeypatch.setattr(db, "get_sessionmaker", lambda: __import__("sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]).async_sessionmaker(_engine, expire_on_commit=False))
>     get_settings.cache_clear()
>     yield
>     get_settings.cache_clear()
> ```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest services/worker/tests/test_sync_bootstrap.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add -A -- ':!docs'
git commit -m "feat: celery worker with idempotent sync_bootstrap task"
```

---

## Task 8: `sync_fixtures` task test + Beat wiring check

**Files:**
- Test: `services/worker/tests/test_sync_fixtures.py`
- Test: `services/worker/tests/test_beat_schedule.py`

- [ ] **Step 1: Write the failing test for fixtures sync**

`services/worker/tests/test_sync_fixtures.py`:
```python
import json
from pathlib import Path

import httpx
import respx
from sqlalchemy import select

from fplguru_core.models import Fixture, Gameweek, Team
from fplguru_worker.tasks import _sync_fixtures

FIXTURES = json.loads(
    (Path(__file__).parents[3] / "packages/ingest/tests/fixtures/fixtures_sample.json").read_text()
)
BASE = "https://fpl.test/api"


@respx.mock
async def test_sync_fixtures_persists_scheduled_and_unscheduled(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    from fplguru_core.settings import get_settings
    get_settings.cache_clear()
    # FK prerequisites
    db_session.add_all([
        Team(id=1, name="Arsenal", short_name="ARS"),
        Gameweek(id=1, name="Gameweek 1", deadline_time="2025-08-15T17:30:00+00:00"),
    ])
    await db_session.commit()
    respx.get(f"{BASE}/fixtures/").mock(return_value=httpx.Response(200, json=FIXTURES))

    await _sync_fixtures()

    rows = (await db_session.execute(select(Fixture).order_by(Fixture.id))).scalars().all()
    assert [r.gameweek_id for r in rows] == [1, None]
```

- [ ] **Step 2: Run to verify it fails, then it should pass immediately**

Run: `python -m pytest services/worker/tests/test_sync_fixtures.py -v`
Expected: PASS (implementation landed in Task 7). If it fails on FK/normalization, fix `_sync_fixtures`/`normalize_fixtures` until green.

- [ ] **Step 3: Write the Beat schedule guard test**

`services/worker/tests/test_beat_schedule.py`:
```python
from fplguru_worker.app import celery_app


def test_beat_schedule_registers_both_sync_jobs():
    sched = celery_app.conf.beat_schedule
    assert sched["sync-bootstrap"]["task"] == "sync_bootstrap"
    assert sched["sync-fixtures"]["task"] == "sync_fixtures"
    assert sched["sync-bootstrap"]["schedule"] <= 900.0
```

Run: `python -m pytest services/worker/tests/test_beat_schedule.py -v`
Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add -A -- ':!docs'
git commit -m "test: sync_fixtures persistence and beat schedule wiring"
```

---

## Task 9: Graceful-degradation error path

**Files:**
- Test: `services/worker/tests/test_sync_error_path.py`

- [ ] **Step 1: Write the failing test**

`services/worker/tests/test_sync_error_path.py`:
```python
import httpx
import pytest
import respx
from sqlalchemy import select

from fplguru_core.models import DataSyncLog
from fplguru_fpl_client import FplApiError
from fplguru_worker.tasks import _sync_bootstrap

BASE = "https://fpl.test/api"


@respx.mock
async def test_api_outage_logs_error_row_and_reraises(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    from fplguru_core.settings import get_settings
    get_settings.cache_clear()
    respx.get(f"{BASE}/bootstrap-static/").mock(return_value=httpx.Response(503))

    with pytest.raises(FplApiError):
        await _sync_bootstrap()

    log = (await db_session.execute(select(DataSyncLog))).scalar_one()
    assert (log.source, log.status) == ("fpl_bootstrap", "error")
    assert "503" in log.detail
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest services/worker/tests/test_sync_error_path.py -v`
Expected: FAIL — currently the FPL error is raised *before* the session opens, so no `DataSyncLog` row is written.

- [ ] **Step 3: Fix `_sync_bootstrap` / `_sync_fixtures` to log fetch failures**

In `tasks.py`, wrap the fetch so a fetch failure also records a row. Replace the fetch block in both `_sync_bootstrap` and `_sync_fixtures` with:
```python
    maker = get_sessionmaker()
    client = FplClient(get_settings().fpl_api_base)
    try:
        data = await client.bootstrap_static()   # or client.fixtures()
    except Exception as exc:  # noqa: BLE001
        async with maker() as session, session.begin():
            await _record(session, "fpl_bootstrap", "error", started, str(exc)[:500])
        raise
    finally:
        await client.aclose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest services/worker/tests/ -v`
Expected: all worker tests pass (5 tests across 4 files).

- [ ] **Step 5: Commit**

```bash
git add -A -- ':!docs'
git commit -m "feat: record DataSyncLog error row when FPL API is unavailable"
```

---

## Task 10: FastAPI service

**Files:**
- Create: `services/api/src/fplguru_api/main.py`
- Test: `services/api/tests/test_api.py`, `services/api/tests/conftest.py`
- Modify: `services/api/pyproject.toml` (deps: `fastapi>=0.111`, `uvicorn[standard]>=0.30`, `fplguru-core`)

- [ ] **Step 1: Add dependencies**

Set `services/api/pyproject.toml` `dependencies = ["fastapi>=0.111", "uvicorn[standard]>=0.30", "fplguru-core"]`, `pip install -r requirements-dev.txt`.

- [ ] **Step 2: Write the failing test**

`services/api/tests/conftest.py`:
```python
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from fplguru_api.main import app, get_db
from fplguru_core.models import Base  # noqa: F401


@pytest_asyncio.fixture
async def client(_engine):
    maker = async_sessionmaker(_engine, expire_on_commit=False)

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    app.dependency_overrides.clear()
```

`services/api/tests/test_api.py`:
```python
from datetime import UTC, datetime

from fplguru_core.models import DataSyncLog, Gameweek


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_gameweeks_and_current(client, db_session):
    db_session.add_all([
        Gameweek(id=1, name="Gameweek 1", deadline_time="2025-08-15T17:30:00+00:00",
                 finished=True),
        Gameweek(id=2, name="Gameweek 2", deadline_time="2025-08-22T17:30:00+00:00",
                 is_current=True),
    ])
    await db_session.commit()

    r = await client.get("/gameweeks")
    assert [g["id"] for g in r.json()] == [1, 2]

    r = await client.get("/gameweeks/current")
    assert r.json()["id"] == 2


async def test_status_reports_last_sync(client, db_session):
    now = datetime(2025, 8, 20, 12, 0, tzinfo=UTC)
    db_session.add(DataSyncLog(source="fpl_bootstrap", status="ok",
                               started_at=now, finished_at=now))
    await db_session.commit()

    r = await client.get("/status")
    body = r.json()
    assert body["sources"]["fpl_bootstrap"]["status"] == "ok"
    assert body["sources"]["fpl_bootstrap"]["as_of"].startswith("2025-08-20T12:00:00")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest services/api/tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: fplguru_api.main`.

- [ ] **Step 4: Write `main.py`**

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from fplguru_core.db import dispose_engine, get_sessionmaker
from fplguru_core.models import DataSyncLog, Gameweek


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


app = FastAPI(title="FPLGuru API", version="0.1.0", lifespan=lifespan)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


def _gw(row: Gameweek) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "deadline_time": row.deadline_time.isoformat(),
        "is_current": row.is_current,
        "is_next": row.is_next,
        "finished": row.finished,
        "average_entry_score": row.average_entry_score,
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/gameweeks")
async def list_gameweeks(db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (await db.execute(select(Gameweek).order_by(Gameweek.id))).scalars().all()
    return [_gw(r) for r in rows]


@app.get("/gameweeks/current")
async def current_gameweek(db: AsyncSession = Depends(get_db)) -> dict | None:
    row = (
        await db.execute(select(Gameweek).where(Gameweek.is_current))
    ).scalar_one_or_none()
    if row is None:
        row = (
            await db.execute(select(Gameweek).where(Gameweek.is_next))
        ).scalar_one_or_none()
    return _gw(row) if row else None


@app.get("/status")
async def status(db: AsyncSession = Depends(get_db)) -> dict:
    sources: dict[str, dict] = {}
    for source in ("fpl_bootstrap", "fpl_fixtures"):
        row = (
            await db.execute(
                select(DataSyncLog)
                .where(DataSyncLog.source == source, DataSyncLog.status == "ok")
                .order_by(desc(DataSyncLog.finished_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        sources[source] = (
            {"status": "ok", "as_of": row.finished_at.isoformat()}
            if row
            else {"status": "unknown", "as_of": None}
        )
    return {"sources": sources}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest services/api/tests/test_api.py -v`
Expected: 4 passed.

- [ ] **Step 6: Manual smoke against real data (optional but recommended)**

```bash
python -m alembic upgrade head
python -c "import asyncio; from fplguru_worker.tasks import _sync_bootstrap; asyncio.run(_sync_bootstrap())"
python -m uvicorn fplguru_api.main:app --port 8000 &
curl -s localhost:8000/gameweeks/current
```
Expected: JSON for the real current/next gameweek.

- [ ] **Step 7: Commit**

```bash
git add -A -- ':!docs'
git commit -m "feat: FastAPI service with health, status, and gameweek endpoints"
```

---

## Task 11: Historical dataset normalizer (for future xP backtesting)

**Files:**
- Create: `packages/ingest/src/fplguru_ingest/historical.py`
- Create: `packages/ingest/tests/fixtures/merged_gw_sample.csv`
- Test: `packages/ingest/tests/test_historical.py`
- Create: `scripts/fetch_historical.py`
- Modify: `packages/ingest/pyproject.toml` (dep: `pandas>=2.2`)

- [ ] **Step 1: Add dependency**

Set `packages/ingest/pyproject.toml` `dependencies = ["fplguru-core", "pandas>=2.2"]`, `pip install -r requirements-dev.txt`.

- [ ] **Step 2: Create a trimmed sample CSV**

`packages/ingest/tests/fixtures/merged_gw_sample.csv` (columns match the `vaastav/Fantasy-Premier-League` `gws/merged_gw.csv` schema, trimmed):
```csv
name,position,team,GW,minutes,goals_scored,assists,clean_sheets,total_points,expected_goals,expected_assists,was_home,opponent_team,value
Bukayo Saka,MID,Arsenal,1,90,1,0,1,9,0.42,0.31,True,15,100
Bukayo Saka,MID,Arsenal,2,78,0,1,0,5,0.20,0.55,False,3,101
```

- [ ] **Step 3: Write the failing test**

`packages/ingest/tests/test_historical.py`:
```python
from pathlib import Path

from fplguru_ingest.historical import normalize_merged_gw

CSV = Path(__file__).parent / "fixtures" / "merged_gw_sample.csv"


def test_normalize_merged_gw_rows():
    rows = normalize_merged_gw(CSV, season="2024-25")
    assert len(rows) == 2
    assert rows[0] == {
        "season": "2024-25",
        "player_name": "Bukayo Saka",
        "position": "MID",
        "team": "Arsenal",
        "gameweek": 1,
        "minutes": 90,
        "goals": 1,
        "assists": 0,
        "clean_sheet": True,
        "total_points": 9,
        "xg": 0.42,
        "xa": 0.31,
        "was_home": True,
        "opponent_team_id": 15,
        "value": 100,
    }
    assert rows[1]["clean_sheet"] is False
    assert rows[1]["was_home"] is False
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest packages/ingest/tests/test_historical.py -v`
Expected: FAIL — `ModuleNotFoundError: fplguru_ingest.historical`.

- [ ] **Step 5: Write `historical.py`**

```python
from pathlib import Path

import pandas as pd


def normalize_merged_gw(csv_path: str | Path, season: str) -> list[dict]:
    df = pd.read_csv(csv_path)
    out: list[dict] = []
    for r in df.itertuples(index=False):
        out.append(
            {
                "season": season,
                "player_name": r.name,
                "position": r.position,
                "team": r.team,
                "gameweek": int(r.GW),
                "minutes": int(r.minutes),
                "goals": int(r.goals_scored),
                "assists": int(r.assists),
                "clean_sheet": int(r.clean_sheets) > 0,
                "total_points": int(r.total_points),
                "xg": float(r.expected_goals),
                "xa": float(r.expected_assists),
                "was_home": bool(r.was_home),
                "opponent_team_id": int(r.opponent_team),
                "value": int(r.value),
            }
        )
    return out
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest packages/ingest/tests/test_historical.py -v`
Expected: 1 passed.

- [ ] **Step 7: Write the downloader script**

`scripts/fetch_historical.py`:
```python
"""Download vaastav/Fantasy-Premier-League merged_gw.csv for the given seasons.

Usage: python scripts/fetch_historical.py 2022-23 2023-24 2024-25
"""
import sys
from pathlib import Path
from urllib.request import urlretrieve

RAW = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{season}/gws/merged_gw.csv"
DEST = Path("data/historical")


def main(seasons: list[str]) -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for season in seasons:
        target = DEST / f"{season}_merged_gw.csv"
        print(f"-> {target}")
        urlretrieve(RAW.format(season=season), target)


if __name__ == "__main__":
    main(sys.argv[1:] or ["2022-23", "2023-24", "2024-25"])
```

Add `data/` to `.gitignore`.

- [ ] **Step 8: Commit**

```bash
git add -A -- ':!docs'
git commit -m "feat: historical merged_gw normalizer and downloader for xP backtests"
```

---

## Task 12: CI pipeline

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: CI
on:
  pull_request:
  push:
    branches: [main]

jobs:
  python:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: fplguru
          POSTGRES_PASSWORD: fplguru
          POSTGRES_DB: fplguru
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready --health-interval 10s
          --health-timeout 5s --health-retries 5
      redis:
        image: redis:7
        ports: ["6379:6379"]
    env:
      FPLGURU_DATABASE_URL: postgresql+asyncpg://fplguru:fplguru@localhost:5432/fplguru
      FPLGURU_TEST_DATABASE_URL: postgresql+asyncpg://fplguru:fplguru@localhost:5432/fplguru_test
      FPLGURU_REDIS_URL: redis://localhost:6379/0
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install --upgrade pip
      - run: python -m pip install -r requirements-dev.txt
      - run: python -m pip install "ruff==0.6.*"
      - run: python -m ruff check .
      - run: python -m alembic upgrade head
      - run: python -m pytest -q

  web:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: corepack enable
      - run: pnpm install --frozen-lockfile
      - run: pnpm --filter web test
      - run: pnpm --filter web build
```

CI runs `ruff` (Linux, no SAC); local dev skips it. `python -m ruff` works because the `ruff` wheel exposes a `__main__`.

- [ ] **Step 2: Verify locally what CI runs (minus ruff)**

Run:
```bash
python -m alembic upgrade head && python -m pytest -q
```
Expected: migrations apply, all Python tests pass. (`ruff` is CI-only — SAC blocks it locally. If you want a local lint proxy, `python -m pyflakes packages services` is pure-Python and runs fine, but it is not required to pass this task.)

- [ ] **Step 3: Commit**

```bash
git add -A -- ':!docs'
git commit -m "ci: lint + migrate + pytest with postgres/redis service containers"
```

---

## Task 13: Next.js PWA shell

**Files:**
- Create: `apps/web/` via `create-next-app`
- Create: `apps/web/public/manifest.json`, `apps/web/src/app/page.tsx`, `apps/web/src/lib/api.ts`
- Test: `apps/web/src/lib/api.test.ts`, `apps/web/vitest.config.ts`

- [ ] **Step 1: Enable pnpm, then scaffold the app**

`pnpm` isn't installed; get it via corepack (bundled with the existing Node):
```bash
corepack enable
corepack prepare pnpm@9 --activate
pnpm --version
```
Then scaffold:
```bash
pnpm create next-app@latest apps/web --ts --tailwind --app --src-dir --no-eslint --use-pnpm --import-alias "@/*"
```
Then from repo root: `pnpm install`.

> **SAC caveat:** `next build` loads the native `@next/swc-win32-x64-msvc` addon. If Smart App Control blocks it (error mentions "Application Control policy"), skip the local `next build` in Step 7 — the `web` CI job builds on Linux where it works. `pnpm --filter web test` (Vitest, pure JS) is unaffected and must still pass locally. Report this as DONE_WITH_CONCERNS if it happens.

- [ ] **Step 2: Add Vitest**

Run: `pnpm --filter web add -D vitest @testing-library/react @testing-library/dom jsdom`

`apps/web/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { environment: "jsdom", globals: true },
});
```
Add to `apps/web/package.json` scripts: `"test": "vitest run"`.

- [ ] **Step 3: Write the failing test**

`apps/web/src/lib/api.test.ts`:
```ts
import { describe, expect, it, vi } from "vitest";
import { fetchStatus } from "./api";

describe("fetchStatus", () => {
  it("returns the parsed status body", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ sources: { fpl_bootstrap: { status: "ok", as_of: "2025-08-20T12:00:00+00:00" } } }),
    }) as unknown as typeof fetch;

    const s = await fetchStatus("http://api.test");
    expect(s.sources.fpl_bootstrap.status).toBe("ok");
  });
});
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pnpm --filter web test`
Expected: FAIL — cannot resolve `./api`.

- [ ] **Step 5: Write `api.ts` and the page**

`apps/web/src/lib/api.ts`:
```ts
export type SyncStatus = {
  sources: Record<string, { status: string; as_of: string | null }>;
};

export async function fetchStatus(base: string): Promise<SyncStatus> {
  const res = await fetch(`${base}/status`, { cache: "no-store" });
  if (!res.ok) throw new Error(`status ${res.status}`);
  return (await res.json()) as SyncStatus;
}
```

`apps/web/src/app/page.tsx`:
```tsx
import { fetchStatus } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export default async function Home() {
  let asOf = "unknown";
  try {
    const s = await fetchStatus(API);
    asOf = s.sources.fpl_bootstrap?.as_of ?? "unknown";
  } catch {
    asOf = "unavailable";
  }
  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">FPLGuru</h1>
      <p className="text-sm text-gray-500">FPL data as of {asOf}</p>
    </main>
  );
}
```

- [ ] **Step 6: Add PWA manifest**

`apps/web/public/manifest.json`:
```json
{
  "name": "FPLGuru",
  "short_name": "FPLGuru",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0b0f19",
  "theme_color": "#0b0f19",
  "icons": [
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```
Reference it in `apps/web/src/app/layout.tsx` metadata: `export const metadata = { manifest: "/manifest.json" }`. (Service worker + install prompt come in sub-plan **P1h**; this task only establishes the manifest.)

- [ ] **Step 7: Run test + build to verify**

Run:
```bash
pnpm --filter web test && pnpm --filter web build
```
Expected: test passes; `next build` succeeds.

- [ ] **Step 8: Commit**

```bash
git add -A -- ':!docs'
git commit -m "feat: next.js PWA shell reading /status with manifest"
```

---

## Task 14: README + acceptance checklist

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
# FPLGuru

FPL tracking + predictive analytics platform. See `docs/plans/` for the build plan.

## Prerequisites
- Python 3.12 from python.org — reachable as `py -3.12` (bare `python` may hit the Windows Store stub; that's fine)
- Node 20+ (pnpm comes via `corepack enable`)
- Docker Desktop (running)

## First run
```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d

py -3.12 -m venv .venv
# activate: source .venv/Scripts/activate  (Git Bash) | .venv\Scripts\Activate.ps1 (PowerShell)
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

python -m alembic upgrade head
# populate DB from the live FPL API
python -c "import asyncio; from fplguru_worker.tasks import _sync_bootstrap, _sync_fixtures; asyncio.run(_sync_bootstrap()); asyncio.run(_sync_fixtures())"
```

## Run services (venv active)
```bash
python -m uvicorn fplguru_api.main:app --reload --port 8000
python -m celery -A fplguru_worker.app.celery_app worker -B --loglevel=info
pnpm --filter web dev
```

## Test
```bash
python -m pytest -q          # lint (ruff) runs in CI only — Smart App Control blocks it locally
pnpm --filter web test
```
````

- [ ] **Step 2: Run the full acceptance checklist**

Verify each and check the box:
- [ ] `docker compose -f infra/docker-compose.yml up -d` → postgres + redis `Up`
- [ ] `.venv` active; `python -m pip install -r requirements-dev.txt` → all 6 local packages install editable, no errors
- [ ] `python -m alembic upgrade head` → 5 tables + `alembic_version` created
- [ ] `python -m pytest -q` → all tests pass (core, fpl_client, ingest, worker, api)
- [ ] CI `python` job green on the PR → includes `python -m ruff check .`
- [ ] Bootstrap populate command → `players`, `teams`, `gameweeks` rows > 0
- [ ] `curl localhost:8000/gameweeks/current` → real current/next GW JSON
- [ ] `curl localhost:8000/status` → `fpl_bootstrap` + `fpl_fixtures` with recent `as_of`
- [ ] `python -m celery ... worker -B` runs; after ~15 min a new `data_sync_log` row appears with `status='ok'`
- [ ] `pnpm --filter web dev` → homepage shows "FPL data as of <timestamp>"

- [ ] **Step 3: Commit**

```bash
git add -A -- ':!docs'
git commit -m "docs: README and Foundation acceptance checklist"
```

---

## Self-Review

**1. Spec coverage (Foundation scope only — PRD §6):**
- §6.1 stack (Postgres, Redis, Python pipeline, FastAPI, Celery) → Tasks 2, 3, 7, 10 ✓
- §6.2 refresh cadence (Beat schedule; live 30–60s polling explicitly deferred to sub-plan P1b) → Task 7 ✓ (live polling out of scope by design)
- §6.3 core entities (`players`, `teams`, `fixtures`, `gameweeks`) → Task 3 ✓; other entities (`users`, `subscriptions`, `player_gw_features`, …) belong to later sub-plans
- §5.6 data sources (Official FPL API + historical dataset for backtesting) → Tasks 5, 11 ✓; Understat is sub-plan P2a
- §7 graceful degradation on FPL API outage → Task 9 + `/status` in Task 10 ✓
- PWA installability shell → Task 13 ✓ (service worker/push deferred to P1h, noted inline)

**2. Placeholder scan:** No "TBD"/"add error handling"/"similar to Task N" — each code step contains complete code. Task 4 Step 2 describes an edit to generated Alembic template rather than pasting the whole file; the specific lines to change are named.

**3. Type consistency:**
- `_upsert(session, model, rows)` signature identical in Task 7 definition and Task 9 reference ✓
- `DataSyncLog` fields (`source`, `status`, `detail`, `started_at`, `finished_at`) consistent across Tasks 3, 7, 9, 10 ✓
- Normalizer output keys in Task 6 (`gameweek_id`, `home_team_id`, `home_difficulty`, …) match `Fixture` columns in Task 3 and the assertions in Task 8 ✓
- `fetchStatus` / `SyncStatus` shape in Task 13 matches `/status` response in Task 10 (`sources.<name>.status`, `.as_of`) ✓

**4. Toolchain (revised from `uv` to `venv`+`pip` after Smart App Control blocked `uv` on the dev machine):**
- No `uv`/`uvx`/`uv run` remain in the plan; every tool is `python -m <tool>` ✓
- Root `pyproject.toml` carries config only; deps live in each package's `pyproject.toml` + `requirements-dev.txt` (editable installs) ✓
- `ruff` removed from local flow, runs in CI only (Linux) ✓
- `pnpm` obtained via `corepack enable` (Task 13) rather than a standalone install ✓
- CI uses `actions/setup-python` + `pip`, not `astral-sh/setup-uv` ✓
- Known residual risk flagged inline: native addons (`@next/swc`, possibly `asyncpg` wheels) may also be SAC-blocked locally → fall back to CI for those pieces, never disable SAC.

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-08-27-foundation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using superpowers:executing-plans, batch execution with checkpoints for review.

Which approach?
