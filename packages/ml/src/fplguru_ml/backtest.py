from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from fplguru_ml.features import FEATURE_NAMES
from fplguru_ml.model_basic import train_basic


@dataclass
class Fold:
    test_gw: int
    train_max_gw: int
    rows: pd.DataFrame  # columns: position, target, pred, baseline


@dataclass
class BacktestResult:
    folds: list[Fold] = field(default_factory=list)

    def _all(self) -> pd.DataFrame:
        if not self.folds:
            return pd.DataFrame(columns=["position", "target", "pred", "baseline"])
        return pd.concat([f.rows for f in self.folds], ignore_index=True)

    def metrics_by_position(self) -> dict[str, dict]:
        df = self._all()
        out: dict[str, dict] = {}
        for pos, g in df.groupby("position"):
            err = g["pred"] - g["target"]
            berr = g["baseline"] - g["target"]
            out[pos] = {
                "n": int(len(g)),
                "mae": float(err.abs().mean()),
                "rmse": float(np.sqrt((err ** 2).mean())),
                "baseline_rmse": float(np.sqrt((berr ** 2).mean())),
            }
        return out


def walk_forward(frame: pd.DataFrame, *, alpha: float = 1.0,
                 min_train_gw: int = 5) -> BacktestResult:
    res = BacktestResult()
    if frame.empty:
        return res
    for test_gw in sorted(frame["gameweek"].unique()):
        train = frame[frame["gameweek"] < test_gw]
        if train.empty or train["gameweek"].nunique() < min_train_gw:
            continue
        test = frame[frame["gameweek"] == test_gw]
        if test.empty:
            continue
        model = train_basic(train, alpha=alpha)
        pos_mean = train.groupby("position")["target"].mean().to_dict()
        overall_mean = float(train["target"].mean())
        parts = []
        for pos, g in test.groupby("position"):
            preds = model.predict_rows(pos, g[FEATURE_NAMES].to_dict("records"))
            parts.append(pd.DataFrame({
                "position": pos,
                "target": g["target"].to_numpy(float),
                "pred": preds,
                "baseline": pos_mean.get(pos, overall_mean),
            }))
        res.folds.append(Fold(int(test_gw), int(train["gameweek"].max()),
                              pd.concat(parts, ignore_index=True)))
    return res
