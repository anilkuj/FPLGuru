import math
from pathlib import Path

import pandas as pd

from fplguru_ml.features import FEATURE_NAMES
from fplguru_ml.frame import build_training_frame

CSV = Path(__file__).parent / "fixtures" / "history_sample.csv"


def _rows():
    return pd.read_csv(CSV).to_dict("records")


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
