from fplguru_core.models import Base, PitchPlayerMap, PitchTeamMap, PlayerXg


def test_pitch_tables_registered_with_keys():
    assert {"pitch_team_map", "pitch_player_map", "player_xg"} <= set(Base.metadata.tables)
    tm = {tuple(sorted(c.name for c in con.columns))
          for con in PitchTeamMap.__table__.constraints
          if con.__class__.__name__ == "UniqueConstraint"}
    assert ("pitch_team_id",) in tm
    pm = {tuple(sorted(c.name for c in con.columns))
          for con in PitchPlayerMap.__table__.constraints
          if con.__class__.__name__ == "UniqueConstraint"}
    assert ("pitch_player_id",) in pm
    xg = {tuple(sorted(c.name for c in con.columns))
          for con in PlayerXg.__table__.constraints
          if con.__class__.__name__ == "UniqueConstraint"}
    assert ("fixture_id", "player_id") in xg
