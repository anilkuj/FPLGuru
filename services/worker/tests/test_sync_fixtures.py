import json
from datetime import datetime
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
    # FK prerequisites
    db_session.add_all([
        Team(id=1, name="Arsenal", short_name="ARS"),
        Gameweek(
            id=1,
            name="Gameweek 1",
            deadline_time=datetime.fromisoformat("2025-08-15T17:30:00+00:00"),
        ),
    ])
    await db_session.commit()
    respx.get(f"{BASE}/fixtures/").mock(return_value=httpx.Response(200, json=FIXTURES))

    await _sync_fixtures()

    rows = (await db_session.execute(select(Fixture).order_by(Fixture.id))).scalars().all()
    assert [r.gameweek_id for r in rows] == [1, None]
