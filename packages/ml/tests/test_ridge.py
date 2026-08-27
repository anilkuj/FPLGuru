import numpy as np

from fplguru_ml.ridge import RidgeModel


def test_recovers_linear_signal():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(400, 3))
    y = 2.0 * X[:, 0] - 1.0 * X[:, 1] + 0.5 + rng.normal(scale=0.01, size=400)
    m = RidgeModel.fit(X, y, feature_names=["a", "b", "c"], alpha=1e-3)
    pred = m.predict(X)
    assert np.sqrt(np.mean((pred - y) ** 2)) < 0.1
    assert abs(m.coef_[0] - 2.0) < 0.2 and abs(m.coef_[2]) < 0.2


def test_json_round_trip():
    X = np.random.default_rng(1).normal(size=(50, 2))
    y = X @ np.array([1.0, -2.0]) + 3.0
    m = RidgeModel.fit(X, y, feature_names=["x", "y"], alpha=0.1)
    m2 = RidgeModel.from_json(m.to_json())
    assert np.allclose(m.predict(X), m2.predict(X))
    assert m2.feature_names == ["x", "y"]


def test_predict_checks_feature_count():
    m = RidgeModel.fit(np.zeros((3, 2)), np.zeros(3), feature_names=["a", "b"], alpha=1.0)
    try:
        m.predict(np.zeros((3, 3)))
    except ValueError:
        return
    raise AssertionError("expected ValueError on wrong feature count")
