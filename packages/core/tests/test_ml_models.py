from fplguru_core.models import Base, PlayerGwFeature, PlayerGwPrediction, PlayerGwStat


def test_ml_tables_registered():
    assert {
        "player_gw_stats",
        "player_gw_features",
        "player_gw_predictions",
    } <= set(Base.metadata.tables)


def test_stat_unique_on_player_gw():
    cols = {c.name for c in PlayerGwStat.__table__.columns}
    assert {
        "player_id",
        "gameweek_id",
        "minutes",
        "total_points",
        "goals",
        "assists",
        "clean_sheets",
    } <= cols
    uqs = [
        c
        for c in PlayerGwStat.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    ]
    assert any({"player_id", "gameweek_id"} == {c.name for c in uq.columns} for uq in uqs)


def test_prediction_has_components_and_horizon():
    cols = {c.name for c in PlayerGwPrediction.__table__.columns}
    assert {"player_id", "gameweek_id", "horizon_gw", "model_version",
            "xp", "x_minutes", "x_goals", "x_assists", "x_cs_or_gc",
            "x_bonus", "xp_floor", "xp_ceiling"} <= cols


def test_feature_row_versioned():
    cols = {c.name for c in PlayerGwFeature.__table__.columns}
    assert {"player_id", "gameweek_id", "feature_set_version", "features"} <= cols
