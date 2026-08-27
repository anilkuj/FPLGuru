import httpx
import pytest
import respx
from sqlalchemy import func, select

from fplguru_core.models import DataSyncLog, Fixture
from fplguru_fpl_client import FplApiError
from fplguru_worker.tasks import _sync_bootstrap, _sync_fixtures

BASE = "https://fpl.test/api"


@respx.mock
async def test_api_outage_logs_error_row_and_reraises(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    respx.get(f"{BASE}/bootstrap-static/").mock(return_value=httpx.Response(503))

    with pytest.raises(FplApiError):
        await _sync_bootstrap()

    log = (await db_session.execute(select(DataSyncLog))).scalar_one()
    assert (log.source, log.status) == ("fpl_bootstrap", "error")
    assert "503" in log.detail


@respx.mock
async def test_fixtures_sync_skips_cleanly_when_no_teams(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    respx.get(f"{BASE}/fixtures/").mock(return_value=httpx.Response(200, json=[]))

    await _sync_fixtures()  # teams table empty -> no FK violation, logs "ok/skipped"

    assert (await db_session.execute(select(func.count()).select_from(Fixture))).scalar() == 0
    log = (await db_session.execute(select(DataSyncLog))).scalar_one()
    assert (log.source, log.status) == ("fpl_fixtures", "ok")
    assert "skipped" in log.detail
