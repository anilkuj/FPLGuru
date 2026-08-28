from datetime import UTC, datetime

from sqlalchemy import select

from fplguru_core.models import (
    Fixture,
    Gameweek,
    PitchPlayerMap,
    PitchTeamMap,
    Player,
    PlayerXg,
    Team,
)
from fplguru_worker import tasks


class _FakePitch:
    def __init__(self, key, base=None, http=None):
        pass

    async def matches_on(self, date):
        return [{"id": "m_1", "status": "finished", "time_utc": f"{date}T15:00:00Z",
                 "home_team": {"id": "t_h", "name": "Home FC"},
                 "away_team": {"id": "t_a", "name": "Away FC"}}]

    async def match_advanced_players(self, mid):
        return [{"player": {"id": "p_1", "name": "E. Home"}, "team_id": "t_h",
                 "minutes_played": 90, "creation": {"xag": 0.3}}]

    async def match_shots(self, mid):
        return [{"player": {"id": "p_1"}, "expected_goals": 0.4}]

    async def aclose(self):
        pass


async def _seed(db_session):
    db_session.add_all([Team(id=1, name="Home FC", short_name="HOM"),
                        Team(id=2, name="Away FC", short_name="AWY")])
    db_session.add(Gameweek(id=5, name="GW5", deadline_time=datetime(2025, 11, 8, tzinfo=UTC),
                            finished=True))
    await db_session.commit()
    db_session.add(Player(id=1, team_id=1, first_name="Erling", second_name="Home",
                          web_name="Home", position="FWD", now_cost=90, status="a"))
    db_session.add(Fixture(id=50, gameweek_id=5, home_team_id=1, away_team_id=2,
                           home_difficulty=3, away_difficulty=3, finished=True,
                           kickoff_time=datetime(2025, 11, 9, 15, 0, tzinfo=UTC)))
    await db_session.commit()


async def test_sync_xg_maps_ids_and_upserts_player_xg(db_session, monkeypatch):
    await _seed(db_session)
    monkeypatch.setattr(tasks, "PitchClient", _FakePitch)
    monkeypatch.setenv("FPLGURU_PITCHAPI_KEY", "pk_test_x")
    await tasks._sync_xg()

    xg = (await db_session.execute(select(PlayerXg))).scalars().all()
    assert len(xg) == 1
    assert xg[0].player_id == 1 and xg[0].fixture_id == 50 and xg[0].gameweek_id == 5
    assert round(xg[0].xg, 2) == 0.4 and xg[0].xag == 0.3 and xg[0].minutes == 90
    assert (await db_session.execute(select(PitchTeamMap))).scalars().first().team_id == 1
    assert (await db_session.execute(
        select(PitchPlayerMap).where(PitchPlayerMap.pitch_player_id == "p_1")
    )).scalar_one().player_id == 1

    await tasks._sync_xg()   # idempotent
    assert len((await db_session.execute(select(PlayerXg))).scalars().all()) == 1


async def test_sync_xg_noop_without_key(db_session, monkeypatch):
    await _seed(db_session)
    monkeypatch.delenv("FPLGURU_PITCHAPI_KEY", raising=False)
    await tasks._sync_xg()
    assert (await db_session.execute(select(PlayerXg))).first() is None
