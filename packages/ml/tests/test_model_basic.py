from pathlib import Path

import pandas as pd

from fplguru_ml.features import FEATURE_NAMES
from fplguru_ml.frame import build_training_frame
from fplguru_ml.model_basic import VERSION, BasicXP, train_basic

CSV = Path(__file__).parent / "fixtures" / "history_sample.csv"


def _frame():
    return build_training_frame(pd.read_csv(CSV).to_dict("records"))


def test_trains_a_model_per_present_position():
    m = train_basic(_frame(), alpha=1.0)
    assert set(m.positions()) <= {"GK", "DEF", "MID", "FWD"}


def test_predict_rows_returns_one_float_per_row():
    m = train_basic(_frame(), alpha=1.0)
    rows = [{k: 0.0 for k in FEATURE_NAMES}, {k: 1.0 for k in FEATURE_NAMES}]
    out = m.predict_rows("MID", rows)
    assert len(out) == 2 and all(isinstance(v, float) for v in out)


def test_unknown_position_uses_global_mean():
    m = train_basic(_frame(), alpha=1.0)
    val = m.predict_rows("GK", [{k: 0.0 for k in m.feature_names}])[0]
    assert isinstance(val, float)


def test_empty_frame_is_safe():
    m = train_basic(pd.DataFrame(), alpha=1.0)
    assert m.positions() == []
    assert m.predict_rows("MID", [{k: 0.0 for k in FEATURE_NAMES}]) == [0.0]


def test_save_load_round_trip(tmp_path):
    m = train_basic(_frame(), alpha=1.0)
    m.save(tmp_path)
    m2 = BasicXP.load(tmp_path)
    r = [{k: 1.0 for k in m.feature_names}]
    assert m2.version == m.version == VERSION
    for pos in m.positions():
        assert abs(m.predict_rows(pos, r)[0] - m2.predict_rows(pos, r)[0]) < 1e-9
