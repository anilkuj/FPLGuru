import json
from pathlib import Path

import httpx
import respx
from sqlalchemy import func, select

from fplguru_core.models import DataSyncLog, Gameweek, Player, Team
from fplguru_worker.tasks import _run_and_dispose, _sync_bootstrap

BOOTSTRAP = json.loads(
    (Path(__file__).parents[3] / "packages/ingest/tests/fixtures/bootstrap_sample.json").read_text()
)
BASE = "https://fpl.test/api"


@respx.mock
async def test_sync_bootstrap_upserts_and_logs(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
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
    respx.get(f"{BASE}/bootstrap-static/").mock(return_value=httpx.Response(200, json=BOOTSTRAP))

    await _sync_bootstrap()
    await _sync_bootstrap()

    assert (await db_session.execute(select(func.count()).select_from(Team))).scalar() == 1
    assert (await db_session.execute(select(func.count()).select_from(Player))).scalar() == 1
    assert (await db_session.execute(select(func.count()).select_from(DataSyncLog))).scalar() == 2


@respx.mock
async def test_run_and_dispose_allows_a_second_run(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    respx.get(f"{BASE}/bootstrap-static/").mock(return_value=httpx.Response(200, json=BOOTSTRAP))

    await _run_and_dispose(_sync_bootstrap)
    await _run_and_dispose(_sync_bootstrap)  # dispose()+reset_state() between runs must not break run 2

    assert (await db_session.execute(select(func.count()).select_from(Player))).scalar() == 1


@respx.mock
async def test_sync_all_runs_both(db_session, monkeypatch):
    from fplguru_worker.tasks import sync_all

    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    respx.get(f"{BASE}/bootstrap-static/").mock(return_value=httpx.Response(200, json=BOOTSTRAP))
    respx.get(f"{BASE}/fixtures/").mock(return_value=httpx.Response(200, json=[]))

    await sync_all()

    from fplguru_core.models import DataSyncLog
    from sqlalchemy import select
    sources = {
        r.source for r in (await db_session.execute(select(DataSyncLog))).scalars().all()
    }
    assert sources == {"fpl_bootstrap", "fpl_fixtures"}
