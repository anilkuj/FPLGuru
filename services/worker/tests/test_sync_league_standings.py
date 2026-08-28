from sqlalchemy import select

from fplguru_core.models import LeagueStanding, LinkedTeam, LinkedTeamLeague
from fplguru_worker import tasks

_STANDINGS = {
    111: {"league": {"name": "Work League"},
          "standings": {"has_next": False, "results": [
              {"entry": 7, "entry_name": "My Team", "player_name": "Sam Q",
               "rank": 1, "last_rank": 2, "total": 500, "event_total": 60},
          ]}},
    222: {"league": {"name": "Cup"},
          "standings": {"has_next": False, "results": [
              {"entry": 8, "entry_name": "Other", "player_name": "Jo K",
               "rank": 3, "last_rank": 3, "total": 400, "event_total": 40},
          ]}},
}


class _FakeClient:
    def __init__(self, base):
        pass

    async def league_standings(self, league_id, page=1):
        return _STANDINGS[league_id]

    async def aclose(self):
        pass


async def _seed(db_session):
    db_session.add_all([
        LinkedTeam(id=1, fpl_entry_id=7, manager_name="Sam"),
        LinkedTeam(id=2, fpl_entry_id=8, manager_name="Jo"),
    ])
    await db_session.commit()
    db_session.add_all([
        LinkedTeamLeague(linked_team_id=1, league_id=111, league_name="Work League"),
        LinkedTeamLeague(linked_team_id=1, league_id=222, league_name="Cup"),
        LinkedTeamLeague(linked_team_id=2, league_id=222, league_name="Cup"),  # shared
    ])
    await db_session.commit()


async def test_sync_league_standings_fetches_each_distinct_league_once(db_session, monkeypatch):
    await _seed(db_session)
    monkeypatch.setattr(tasks, "FplClient", _FakeClient)
    await tasks._sync_league_standings()

    rows = (await db_session.execute(
        select(LeagueStanding).order_by(LeagueStanding.league_id)
    )).scalars().all()
    assert [(r.league_id, r.entry_id, r.rank) for r in rows] == [(111, 7, 1), (222, 8, 3)]

    await tasks._sync_league_standings()   # idempotent
    rows = (await db_session.execute(select(LeagueStanding))).scalars().all()
    assert len(rows) == 2
