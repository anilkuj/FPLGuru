from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from fplguru_ml.features import FEATURE_NAMES, FEATURE_NAMES_ADV
from fplguru_ml.model_advanced import train_advanced
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


def _strided_test_gws(frame: pd.DataFrame, min_train_gw: int, gw_stride: int) -> set:
    eligible = [gw for gw in sorted(frame["gameweek"].unique())
                if frame[frame["gameweek"] < gw]["gameweek"].nunique() >= min_train_gw]
    return set(eligible[::max(1, gw_stride)])


def walk_forward(frame: pd.DataFrame, *, alpha: float = 1.0,
                 min_train_gw: int = 5, gw_stride: int = 1) -> BacktestResult:
    res = BacktestResult()
    if frame.empty:
        return res
    keep = _strided_test_gws(frame, min_train_gw, gw_stride)
    for test_gw in sorted(frame["gameweek"].unique()):
        if test_gw not in keep:
            continue
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


def walk_forward_adv(frame: pd.DataFrame, *, min_train_gw: int = 5,
                     min_rows: int = 200, gw_stride: int = 1,
                     **gbrt_kw) -> BacktestResult:
    """Walk-forward backtest of AdvancedXP. `frame` must carry FEATURE_NAMES_ADV.

    `gw_stride` > 1 evaluates only every Nth eligible test gameweek — the
    pure-numpy GBRT is slow to refit, and a strided sweep is enough for a
    directional adv-vs-basic RMSE comparison.
    """
    res = BacktestResult()
    if frame.empty:
        return res
    keep = _strided_test_gws(frame, min_train_gw, gw_stride)
    for test_gw in sorted(frame["gameweek"].unique()):
        if test_gw not in keep:
            continue
        train = frame[frame["gameweek"] < test_gw]
        if train.empty or train["gameweek"].nunique() < min_train_gw:
            continue
        test = frame[frame["gameweek"] == test_gw]
        if test.empty:
            continue
        model = train_advanced(train, min_rows=min_rows, **gbrt_kw)
        pos_mean = train.groupby("position")["target"].mean().to_dict()
        overall_mean = float(train["target"].mean())
        parts = []
        for pos, g in test.groupby("position"):
            preds = model.predict_rows(pos, g[FEATURE_NAMES_ADV].to_dict("records"))
            parts.append(pd.DataFrame({
                "position": pos,
                "target": g["target"].to_numpy(float),
                "pred": preds,
                "baseline": pos_mean.get(pos, overall_mean),
            }))
        res.folds.append(Fold(int(test_gw), int(train["gameweek"].max()),
                              pd.concat(parts, ignore_index=True)))
    return res
