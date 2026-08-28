"""Point-prediction accuracy metrics (projection vs actual)."""
from __future__ import annotations

from collections.abc import Iterable

import numpy as np


def pointwise_metrics(pairs: Iterable[tuple[float, float]]) -> dict:
    """`pairs` = (predicted, actual). Returns n / mae / rmse / bias (mean signed
    error, pred - actual). Empty input returns a zeroed dict."""
    arr = np.array([(float(p), float(a)) for p, a in pairs], dtype=float)
    if arr.size == 0:
        return {"n": 0, "mae": 0.0, "rmse": 0.0, "bias": 0.0}
    err = arr[:, 0] - arr[:, 1]
    return {
        "n": int(len(err)),
        "mae": float(np.abs(err).mean()),
        "rmse": float(np.sqrt((err ** 2).mean())),
        "bias": float(err.mean()),
    }
