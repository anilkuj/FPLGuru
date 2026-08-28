def test_player_has_trend_columns():
    from fplguru_core.models import Player

    cols = {c.name for c in Player.__table__.columns}
    assert {"transfers_in_event", "transfers_out_event", "cost_change_event", "form"} <= cols
