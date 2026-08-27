from fplguru_ml.features import FEATURE_NAMES, feature_row_from_history


def test_feature_names_stable():
    assert FEATURE_NAMES == [
        "form_points_3", "form_points_5", "form_minutes_3", "starts_rate_5",
        "form_goals_5", "form_assists_5", "was_home", "value", "opp_conceded_to_pos_5",
    ]


def test_feature_row_from_history_matches_frame_semantics():
    history = [
        {"total_points": 8, "minutes": 90, "goals": 1, "assists": 0},
        {"total_points": 6, "minutes": 90, "goals": 0, "assists": 1},
        {"total_points": 2, "minutes": 80, "goals": 0, "assists": 0},
    ]
    row = feature_row_from_history(
        history,
        was_home=True,
        value=101,
        opp_conceded_to_pos_5=3.5,
    )
    assert set(row) == set(FEATURE_NAMES)
    assert abs(row["form_points_3"] - (8 * 1 + 6 * 2 + 2 * 3) / 6) < 1e-9
    assert row["was_home"] == 1.0 and row["value"] == 101.0


def test_too_few_appearances_returns_none():
    assert feature_row_from_history(
        [{"total_points": 3, "minutes": 90, "goals": 0, "assists": 0}],
        was_home=False, value=50, opp_conceded_to_pos_5=0.0,
    ) is None
