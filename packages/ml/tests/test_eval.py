import math

from fplguru_ml.eval import pointwise_metrics


def test_metrics_on_known_pairs():
    # (pred, actual) -> errors -1, +1, 0, +2
    m = pointwise_metrics([(4, 5), (6, 5), (3, 3), (7, 5)])
    assert m["n"] == 4
    assert math.isclose(m["mae"], (1 + 1 + 0 + 2) / 4)
    assert math.isclose(m["rmse"], math.sqrt((1 + 1 + 0 + 4) / 4))
    assert math.isclose(m["bias"], (-1 + 1 + 0 + 2) / 4)


def test_metrics_empty_is_zeroed():
    assert pointwise_metrics([]) == {"n": 0, "mae": 0.0, "rmse": 0.0, "bias": 0.0}


def test_metrics_accepts_generator():
    m = pointwise_metrics((p, a) for p, a in [(2.0, 2.0), (5.0, 3.0)])
    assert m["n"] == 2 and math.isclose(m["mae"], 1.0)
