from fplguru_core.models import Base, Fixture, PlayerGwLive


def test_player_gw_live_registered_with_unique_key():
    assert "player_gw_live" in Base.metadata.tables
    uqs = {
        tuple(sorted(c.name for c in con.columns))
        for con in PlayerGwLive.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    }
    assert ("gameweek_id", "player_id") in uqs


def test_fixture_has_match_state_columns():
    cols = {c.name for c in Fixture.__table__.columns}
    assert {"started", "finished_provisional", "minutes"} <= cols
