import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx
from sqlalchemy import select

from fplguru_core.models import Fixture, Gameweek, Player, PlayerGwStat, Team
from fplguru_worker.tasks import _sync_gw_stats

_FIXTURE = Path(__file__).parents[3] / "packages/ingest/tests/fixtures/event_live_sample.json"
EVENT_LIVE = json.loads(_FIXTURE.read_text())
BASE = "https://fpl.test/api"


@respx.mock
async def test_sync_gw_stats_upserts_finished_gws(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    # Seed FK parents before children: these models declare no relationship(),
    # so the ORM unit-of-work would otherwise flush mappers alphabetically.
    db_session.add_all([
        Team(id=1, name="A", short_name="A"), Team(id=2, name="B", short_name="B"),
        Gameweek(id=7, name="GW7", deadline_time=datetime(2025, 10, 1, tzinfo=UTC), finished=True),
        Gameweek(id=8, name="GW8", deadline_time=datetime(2025, 10, 8, tzinfo=UTC), finished=False),
    ])
    await db_session.flush()
    db_session.add_all([
        Player(id=11, team_id=1, first_name="x", second_name="y", web_name="xy",
               position="MID", now_cost=100, status="a", selected_by_percent=1.0, total_points=9),
        Player(id=12, team_id=2, first_name="p", second_name="q", web_name="pq",
               position="DEF", now_cost=45, status="a", selected_by_percent=1.0, total_points=0),
    ])
    await db_session.flush()
    db_session.add(
        Fixture(id=70, gameweek_id=7, home_team_id=1, away_team_id=2,
                home_difficulty=3, away_difficulty=3, finished=True),
    )
    await db_session.commit()
    route7 = respx.get(f"{BASE}/event/7/live/").mock(
        return_value=httpx.Response(200, json=EVENT_LIVE)
    )
    route8 = respx.get(f"{BASE}/event/8/live/").mock(
        return_value=httpx.Response(200, json=EVENT_LIVE)
    )

    await _sync_gw_stats()

    result = await db_session.execute(
        select(PlayerGwStat).order_by(PlayerGwStat.player_id)
    )
    rows = result.scalars().all()
    assert [(r.player_id, r.gameweek_id, r.total_points) for r in rows] == [(11, 7, 9), (12, 7, 0)]
    # player 11 (team 1) home vs team 2
    assert rows[0].was_home is True and rows[0].opponent_team_id == 2
    assert rows[1].was_home is False and rows[1].opponent_team_id == 1
    assert rows[0].value == 100
    assert route7.called and not route8.called   # GW8 not finished -> not fetched


@respx.mock
async def test_sync_gw_stats_is_idempotent(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    db_session.add_all([
        Team(id=1, name="A", short_name="A"), Team(id=2, name="B", short_name="B"),
        Gameweek(id=7, name="GW7", deadline_time=datetime(2025, 10, 1, tzinfo=UTC), finished=True),
    ])
    await db_session.flush()
    db_session.add(
        Player(id=11, team_id=1, first_name="x", second_name="y", web_name="xy",
               position="MID", now_cost=100, status="a", selected_by_percent=1.0, total_points=9),
    )
    await db_session.flush()
    db_session.add(
        Fixture(id=70, gameweek_id=7, home_team_id=1, away_team_id=2,
                home_difficulty=3, away_difficulty=3, finished=True),
    )
    await db_session.commit()
    respx.get(f"{BASE}/event/7/live/").mock(return_value=httpx.Response(200, json=EVENT_LIVE))

    await _sync_gw_stats()
    await _sync_gw_stats()

    from sqlalchemy import func
    n = (await db_session.execute(
        select(func.count()).select_from(PlayerGwStat).where(PlayerGwStat.player_id == 11)
    )).scalar()
    assert n == 1
