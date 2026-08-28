import math
from pathlib import Path

import pandas as pd

from fplguru_ml.features import FEATURE_NAMES, FEATURE_NAMES_ADV
from fplguru_ml.frame import build_adv_frame, build_training_frame

CSV = Path(__file__).parent / "fixtures" / "history_sample.csv"
ADV_CSV = Path(__file__).parent / "fixtures" / "history_adv_sample.csv"


def _rows():
    return pd.read_csv(CSV).to_dict("records")


def _adv_rows():
    return pd.read_csv(ADV_CSV).to_dict("records")


def test_frame_has_feature_cols_and_target():
    df = build_training_frame(_rows())
    assert set(FEATURE_NAMES) <= set(df.columns)
    assert "target" in df.columns and "position" in df.columns


def test_rolling_is_leak_free_and_shifted():
    df = build_training_frame(_rows())
    saka = df[df.player_name == "Saka"].sort_values("gameweek")
    # GW4 row: form over prior 3 appearances (GW1,2,3 points 8,6,2), recency weights 1,2,3
    row4 = saka[saka.gameweek == 4].iloc[0]
    assert math.isclose(row4["form_points_3"], (8 * 1 + 6 * 2 + 2 * 3) / 6, rel_tol=1e-6)
    assert row4["target"] == 13
    # GW1/GW2/GW3 rows have < 3 prior appearances -> dropped
    assert saka.gameweek.min() == 4


def test_opp_conceded_to_pos_is_present():
    df = build_training_frame(_rows())
    assert "opp_conceded_to_pos_5" in df.columns


def test_adv_frame_has_all_adv_feature_cols():
    df = build_adv_frame(_adv_rows())
    assert set(FEATURE_NAMES_ADV) <= set(df.columns)
    assert "target" in df.columns


def test_adv_frame_xg_features_are_leak_free():
    df = build_adv_frame(_adv_rows())
    saka4 = df[(df.player_name == "Saka") & (df.gameweek == 4)].iloc[0]
    # prior appearances GW1-3: xg [0.40, 0.20, 0.10], goals [1, 0, 0]
    assert math.isclose(saka4["form_xg_5"], (0.40 + 0.20 + 0.10) / 3, rel_tol=1e-9)
    assert math.isclose(saka4["form_xa_5"], (0.10 + 0.50 + 0.15) / 3, rel_tol=1e-9)
    # overperf = goals - xg = [0.60, -0.20, -0.10] -> mean 0.10
    assert math.isclose(saka4["xg_overperf_5"], (0.60 - 0.20 - 0.10) / 3, rel_tol=1e-9)
    assert math.isclose(saka4["form_ict_5"], (9.0 + 7.0 + 4.0) / 3, rel_tol=1e-9)


def test_adv_frame_falls_back_to_zero_without_xg_columns():
    df = build_adv_frame(_rows())  # basic fixture has no xg/xa columns
    assert set(FEATURE_NAMES_ADV) <= set(df.columns)
    assert (df["form_xg_5"] == 0.0).all()
