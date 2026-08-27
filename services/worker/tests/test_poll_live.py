from datetime import UTC, datetime

from sqlalchemy import select

from fplguru_core.models import Fixture, Gameweek, Player, PlayerGwLive, Team
from fplguru_worker import tasks

_LIVE_PAYLOAD = {
    "elements": [
        {"id": 1, "stats": {"minutes": 90, "total_points": 9, "bps": 40},
         "explain": [{"fixture": 500, "stats": [{"identifier": "bps", "value": 40}]}]},
        {"id": 2, "stats": {"minutes": 90, "total_points": 4, "bps": 22},
         "explain": [{"fixture": 500, "stats": [{"identifier": "bps", "value": 22}]}]},
        {"id": 3, "stats": {"minutes": 0, "total_points": 0, "bps": 0}, "explain": []},
    ]
}


class _FakeClient:
    def __init__(self, base, *, fixtures, live):
        self._fixtures = fixtures
        self._live = live

    async def fixtures(self):
        return self._fixtures

    async def event_live(self, gw):
        return self._live

    async def aclose(self):
        pass


async def _seed(db_session, *, started):
    db_session.add_all([
        Team(id=1, name="A", short_name="AAA"),
        Team(id=2, name="B", short_name="BBB"),
    ])
    db_session.add(Gameweek(id=3, name="GW3", deadline_time=datetime(2025, 9, 1, tzinfo=UTC),
                            is_current=True))
    await db_session.commit()
    db_session.add_all([
        Player(id=1, team_id=1, first_name="p", second_name="one", web_name="P1",
               position="MID", now_cost=70, status="a"),
        Player(id=2, team_id=2, first_name="p", second_name="two", web_name="P2",
               position="DEF", now_cost=50, status="a"),
        Player(id=3, team_id=2, first_name="p", second_name="three", web_name="P3",
               position="FWD", now_cost=60, status="a"),
    ])
    await db_session.commit()
    return [{"id": 500, "event": 3, "kickoff_time": "2025-09-01T14:00:00Z",
             "team_h": 1, "team_a": 2, "team_h_difficulty": 3, "team_a_difficulty": 3,
             "finished": False, "team_h_score": 1, "team_a_score": 0,
             "started": started, "minutes": 70 if started else 0,
             "finished_provisional": False}]


async def test_poll_live_writes_projection_when_match_in_play(db_session, monkeypatch):
    fixtures = await _seed(db_session, started=True)
    monkeypatch.setattr(tasks, "FplClient",
                        lambda base: _FakeClient(base, fixtures=fixtures, live=_LIVE_PAYLOAD))
    await tasks._poll_live()

    rows = {r.player_id: r for r in (await db_session.execute(select(PlayerGwLive))).scalars()}
    assert set(rows) == {1, 2}                       # player 3 did not feature
    assert rows[1].projected_bonus == 3             # top BPS in fixture 500
    assert rows[2].projected_bonus == 2
    assert rows[1].total_points == 9 + 3
    fx = (await db_session.execute(select(Fixture).where(Fixture.id == 500))).scalar_one()
    assert fx.started is True and fx.home_score == 1 and fx.minutes == 70


async def test_poll_live_noop_when_no_match_in_play(db_session, monkeypatch):
    fixtures = await _seed(db_session, started=False)
    monkeypatch.setattr(tasks, "FplClient",
                        lambda base: _FakeClient(base, fixtures=fixtures, live=_LIVE_PAYLOAD))
    await tasks._poll_live()

    assert (await db_session.execute(select(PlayerGwLive))).first() is None
