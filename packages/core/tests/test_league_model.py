from fplguru_core.models import Base, LeagueStanding, LinkedTeamLeague


def test_league_tables_registered_with_unique_keys():
    assert {"linked_team_leagues", "league_standings"} <= set(Base.metadata.tables)
    ltl = {tuple(sorted(c.name for c in con.columns))
           for con in LinkedTeamLeague.__table__.constraints
           if con.__class__.__name__ == "UniqueConstraint"}
    assert ("league_id", "linked_team_id") in ltl
    ls = {tuple(sorted(c.name for c in con.columns))
          for con in LeagueStanding.__table__.constraints
          if con.__class__.__name__ == "UniqueConstraint"}
    assert ("entry_id", "league_id") in ls
