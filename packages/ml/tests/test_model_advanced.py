import numpy as np
import pandas as pd

from fplguru_ml.features import FEATURE_NAMES_ADV
from fplguru_ml.model_advanced import VERSION, AdvancedXP, train_advanced


def _frame(n_per_pos=160, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for pos, scale in (("MID", 4.0), ("DEF", 3.0)):
        x = rng.normal(size=(n_per_pos, len(FEATURE_NAMES_ADV)))
        # non-linear target so GBRT has something to learn
        y = scale + 2.0 * (x[:, 0] > 0) + np.sin(x[:, 4]) * 1.5 + 0.4 * rng.normal(size=n_per_pos)
        for i in range(n_per_pos):
            r = {k: float(x[i, j]) for j, k in enumerate(FEATURE_NAMES_ADV)}
            r.update(position=pos, gameweek=1 + i % 20, target=float(y[i]))
            rows.append(r)
    return pd.DataFrame(rows)


def test_train_advanced_predicts_and_bands_bracket_mean():
    frame = _frame()
    model = train_advanced(frame, min_rows=50, n_estimators=40, seed=1)
    assert model.version == VERSION
    assert set(model.positions()) == {"MID", "DEF"}
    rows = frame[frame.position == "MID"][FEATURE_NAMES_ADV].to_dict("records")[:20]
    mid = np.array(model.predict_rows("MID", rows))
    lo, hi = model.predict_bands("MID", rows)
    lo, hi = np.array(lo), np.array(hi)
    assert mid.shape == (20,)
    assert np.all(lo <= mid + 1e-9) and np.all(hi >= mid - 1e-9)
    assert np.mean(hi - lo) > 0


def test_advanced_baseline_and_unknown_position():
    frame = _frame()
    model = train_advanced(frame, min_rows=50, n_estimators=20, seed=2)
    assert abs(model.baseline("MID") - frame[frame.position == "MID"].target.mean()) < 1e-9
    # unknown position -> baseline fallback, no crash
    assert model.predict_rows("FWD", [{k: 0.0 for k in FEATURE_NAMES_ADV}]) == [
        model.baseline("FWD")
    ]


def test_advanced_save_load_round_trip(tmp_path):
    frame = _frame()
    model = train_advanced(frame, min_rows=50, n_estimators=25, seed=3)
    model.save(tmp_path / "adv")
    reloaded = AdvancedXP.load(tmp_path / "adv")
    rows = frame[frame.position == "DEF"][FEATURE_NAMES_ADV].to_dict("records")[:15]
    assert np.allclose(model.predict_rows("DEF", rows), reloaded.predict_rows("DEF", rows))
    a_lo, a_hi = model.predict_bands("DEF", rows)
    b_lo, b_hi = reloaded.predict_bands("DEF", rows)
    assert np.allclose(a_lo, b_lo) and np.allclose(a_hi, b_hi)


def test_train_advanced_empty_frame():
    model = train_advanced(pd.DataFrame())
    assert model.positions() == []
    assert model.predict_rows("MID", []) == []


def test_explain_row_ranks_drivers_by_prediction_delta():
    frame = _frame()
    model = train_advanced(frame, min_rows=50, n_estimators=40, seed=1)
    row = frame[frame.position == "MID"][FEATURE_NAMES_ADV].to_dict("records")[0]
    drivers = model.explain_row("MID", row, top=3)
    assert len(drivers) == 3
    for name, delta in drivers:
        assert name in FEATURE_NAMES_ADV
        assert isinstance(delta, float)
    mags = [abs(d) for _, d in drivers]
    assert mags == sorted(mags, reverse=True)
    # unknown position -> no drivers, no crash
    assert model.explain_row("XXX", row) == []


def test_feature_medians_persist(tmp_path):
    frame = _frame()
    model = train_advanced(frame, min_rows=50, n_estimators=20, seed=2)
    model.save(tmp_path / "adv")
    reloaded = AdvancedXP.load(tmp_path / "adv")
    assert set(reloaded.feature_medians()) == set(model.positions())
    assert len(reloaded.feature_medians()["MID"]) == len(FEATURE_NAMES_ADV)
