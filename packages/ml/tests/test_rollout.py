from fplguru_ml.features import FEATURE_NAMES
from fplguru_ml.rollout import project_horizon


class _StubModel:
    version = "stub"
    feature_names = FEATURE_NAMES

    def predict_rows(self, position, rows):
        return [3.0 for _ in rows]


def test_projects_each_gw_and_cumulates():
    per_gw = [{k: 0.0 for k in FEATURE_NAMES} for _ in range(5)]
    hp = project_horizon("MID", per_gw, _StubModel())
    assert [round(p.xp, 3) for p in hp.per_gw] == [3.0, 3.0, 3.0, 3.0, 3.0]
    assert round(hp.cumulative, 3) == 15.0
    assert hp.per_gw[0].horizon_gw == 1 and hp.per_gw[4].horizon_gw == 5


def test_band_halfwidth_grows():
    from fplguru_ml.rollout import band_halfwidth
    assert band_halfwidth(1) == 2.0
    assert band_halfwidth(5) > band_halfwidth(1)


def test_confidence_band_widens_with_horizon():
    per_gw = [{k: 0.0 for k in FEATURE_NAMES} for _ in range(5)]
    hp = project_horizon("MID", per_gw, _StubModel())
    spreads = [p.ceiling - p.floor for p in hp.per_gw]
    assert spreads == sorted(spreads) and spreads[4] > spreads[0]
