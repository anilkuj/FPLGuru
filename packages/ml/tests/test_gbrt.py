import numpy as np

from fplguru_ml.gbrt import GBRT


def _data(n=600, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 3))
    # non-linear target: a step in x0 plus a sine in x1 — ridge cannot fit this
    y = (x[:, 0] > 0).astype(float) * 3 + np.sin(x[:, 1]) * 2 + 0.3 * rng.normal(size=n)
    return x, y


def test_gbrt_fits_nonlinear_signal_and_beats_mean():
    x, y = _data()
    m = GBRT.fit(x, y, n_estimators=80, learning_rate=0.1, max_depth=3, seed=1)
    pred = m.predict(x)
    rmse = float(np.sqrt(np.mean((pred - y) ** 2)))
    base = float(np.sqrt(np.mean((y.mean() - y) ** 2)))
    assert rmse < 0.6 * base


def test_gbrt_json_round_trip_is_exact():
    x, y = _data(200)
    m = GBRT.fit(x, y, n_estimators=20, learning_rate=0.2, max_depth=2, seed=2)
    m2 = GBRT.from_json(m.to_json())
    assert np.allclose(m.predict(x), m2.predict(x))


def test_gbrt_quantile_brackets_the_mean():
    x, y = _data(800)
    lo = GBRT.fit(x, y, n_estimators=60, learning_rate=0.1, max_depth=3, seed=3,
                  loss="quantile", alpha=0.15)
    hi = GBRT.fit(x, y, n_estimators=60, learning_rate=0.1, max_depth=3, seed=3,
                  loss="quantile", alpha=0.85)
    plo, phi = lo.predict(x), hi.predict(x)
    cover = float(np.mean((y >= plo) & (y <= phi)))
    # nominal coverage for a [0.15, 0.85] band is 0.70; the shrinkage from a
    # modest tree budget leaves the band a little wide, which is the safe
    # direction for a floor/ceiling.
    assert 0.55 < cover < 0.96
    assert np.mean(phi - plo) > 0


def test_gbrt_predict_shape_and_determinism():
    x, y = _data(150)
    a = GBRT.fit(x, y, n_estimators=15, seed=7)
    b = GBRT.fit(x, y, n_estimators=15, seed=7)
    assert a.predict(x).shape == (150,)
    assert np.allclose(a.predict(x), b.predict(x))
