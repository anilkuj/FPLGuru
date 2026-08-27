from fplguru_core.models import Base, EntryGwHistory, EntryPick, LinkedTeam


def test_entry_tables_registered():
    assert {"linked_teams", "entry_gw_history", "entry_picks"} <= set(Base.metadata.tables)


def test_linked_team_unique_on_entry_id():
    uqs = [
        c for c in LinkedTeam.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    ]
    assert any({"fpl_entry_id"} == {c.name for c in uq.columns} for uq in uqs)


def test_pick_columns():
    cols = {c.name for c in EntryPick.__table__.columns}
    assert {"linked_team_id", "gameweek_id", "player_id", "slot", "multiplier",
            "is_captain", "is_vice"} <= cols


def test_history_columns():
    cols = {c.name for c in EntryGwHistory.__table__.columns}
    assert {"linked_team_id", "gameweek_id", "points", "total_points", "overall_rank",
            "bank", "team_value", "transfers", "transfer_cost", "points_on_bench"} <= cols
