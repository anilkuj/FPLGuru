from fplguru_core.models import Base, Fixture, Player


def test_expected_tables_registered():
    assert set(Base.metadata.tables) == {
        "teams", "gameweeks", "players", "fixtures", "data_sync_log",
        "player_gw_stats", "player_gw_features", "player_gw_predictions",
        "linked_teams", "entry_gw_history", "entry_picks",
        "player_gw_live", "alerts", "push_subscriptions",
        "linked_team_leagues", "league_standings",
    }


def test_player_has_availability_columns():
    cols = {c.name for c in Player.__table__.columns}
    assert {"status", "chance_of_playing_next_round", "news", "position", "team_id"} <= cols


def test_fixture_gameweek_is_nullable_for_unscheduled():
    assert Fixture.__table__.c.gameweek_id.nullable is True
