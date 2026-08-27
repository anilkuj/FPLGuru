import json
from datetime import UTC, datetime

from fplguru_core.models import Fixture, Gameweek, Player, PlayerGwLive, Team


async def _seed(db_session):
    db_session.add_all([
        Team(id=1, name="A", short_name="AAA", strength_overall_home=3, strength_overall_away=3),
        Team(id=2, name="B", short_name="BBB", strength_overall_home=3, strength_overall_away=3),
    ])
    db_session.add(Gameweek(id=3, name="GW3", deadline_time=datetime(2025, 9, 1, tzinfo=UTC),
                            is_current=True))
    await db_session.commit()
    db_session.add_all([
        Player(id=1, team_id=1, first_name="p", second_name="one", web_name="P1",
               position="MID", now_cost=70, status="a"),
        Player(id=2, team_id=2, first_name="p", second_name="two", web_name="P2",
               position="DEF", now_cost=50, status="a"),
        Fixture(id=500, gameweek_id=3, home_team_id=1, away_team_id=2, home_difficulty=3,
                away_difficulty=3, finished=False, home_score=1, away_score=0,
                started=True, minutes=70),
    ])
    await db_session.commit()
    db_session.add_all([
        PlayerGwLive(player_id=1, gameweek_id=3, minutes=90, live_points=9, bps=40,
                     projected_bonus=3, total_points=12),
        PlayerGwLive(player_id=2, gameweek_id=3, minutes=90, live_points=4, bps=22,
                     projected_bonus=2, total_points=6),
    ])
    await db_session.commit()


async def test_live_snapshot_ranks_players_and_lists_fixtures(client, db_session):
    await _seed(db_session)
    body = (await client.get("/gameweeks/current/live")).json()
    assert body["gameweek_id"] == 3
    assert body["updated_at"] is not None
    assert [p["player_id"] for p in body["players"]] == [1, 2]   # total_points desc
    assert body["players"][0]["projected_bonus"] == 3
    assert body["players"][0]["web_name"] == "P1"
    assert body["fixtures"][0]["id"] == 500
    assert body["fixtures"][0]["started"] is True
    assert body["fixtures"][0]["home_score"] == 1


async def test_live_snapshot_empty_when_no_current_gameweek(client, db_session):
    body = (await client.get("/gameweeks/current/live")).json()
    assert body == {"gameweek_id": None, "updated_at": None, "fixtures": [], "players": []}


class _FakeDisconnectedRequest:
    async def is_disconnected(self) -> bool:
        return True


async def test_live_stream_first_event_is_a_snapshot(db_session):
    # httpx ASGITransport buffers responses, so drive the generator directly.
    from fplguru_api.main import _live_event_stream

    await _seed(db_session)
    gen = _live_event_stream(_FakeDisconnectedRequest(), poll_seconds=0)
    try:
        chunk = await gen.__anext__()
    finally:
        await gen.aclose()
    assert chunk.startswith("data: ")
    payload = json.loads(chunk[len("data: "):].strip())
    assert payload["gameweek_id"] == 3
    assert payload["players"][0]["player_id"] == 1


async def test_live_stream_route_sets_sse_headers():
    from fplguru_api.main import live_stream

    resp = await live_stream(_FakeDisconnectedRequest())
    assert resp.media_type == "text/event-stream"
    assert resp.headers["cache-control"] == "no-cache"
