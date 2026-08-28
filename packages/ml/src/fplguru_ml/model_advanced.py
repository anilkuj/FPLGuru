"""Advanced xP model: one L2 GBRT for the mean plus two quantile GBRTs for a
floor/ceiling band, per position. Same save/load layout as ``BasicXP`` but with
`<POS>.{mean,lo,hi}.json` artifacts and the `FEATURE_NAMES_ADV` feature set.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fplguru_ml.features import FEATURE_NAMES_ADV
from fplguru_ml.gbrt import GBRT

VERSION = "adv-v1"
_LO, _HI = 0.15, 0.85
_MIN_ROWS = 200


class AdvancedXP:
    def __init__(self, mean_models, lo_models, hi_models, global_mean,
                 pos_means=None, version: str = VERSION,
                 feature_medians=None) -> None:
        self._mean = dict(mean_models)
        self._lo = dict(lo_models)
        self._hi = dict(hi_models)
        self._global_mean = float(global_mean)
        self._pos_means = dict(pos_means or {})
        self._medians = {k: [float(x) for x in v]
                         for k, v in (feature_medians or {}).items()}
        self.version = version
        self.feature_names = list(FEATURE_NAMES_ADV)

    def positions(self) -> list[str]:
        return sorted(self._mean)

    def baseline(self, position: str) -> float:
        return float(self._pos_means.get(position, self._global_mean))

    def feature_medians(self) -> dict[str, list[float]]:
        return {k: list(v) for k, v in self._medians.items()}

    def explain_row(self, position: str, row: dict,
                    *, top: int = 3) -> list[tuple[str, float]]:
        """Local occlusion attribution: for each feature, swap in this position's
        training-set median and measure how the mean prediction moves. A positive
        delta means the feature's actual value pushed the projection *up*.
        Returns the `top` features by absolute effect."""
        m = self._mean.get(position)
        if m is None:
            return []
        base = [float(row[k]) for k in self.feature_names]
        meds = self._medians.get(position) or base
        p0 = float(m.predict([base])[0])
        out: list[tuple[str, float]] = []
        for i, name in enumerate(self.feature_names):
            if abs(base[i] - meds[i]) < 1e-12:
                continue
            swapped = list(base)
            swapped[i] = meds[i]
            delta = p0 - float(m.predict([swapped])[0])
            out.append((name, round(delta, 4)))
        out.sort(key=lambda t: abs(t[1]), reverse=True)
        return out[:top]

    def _x(self, rows: list[dict]) -> np.ndarray:
        return np.array([[float(r[k]) for k in self.feature_names] for r in rows], float)

    def predict_rows(self, position: str, rows: list[dict]) -> list[float]:
        if not rows:
            return []
        m = self._mean.get(position)
        if m is None:
            return [self.baseline(position)] * len(rows)
        return [float(v) for v in m.predict(self._x(rows))]

    def predict_bands(self, position: str, rows: list[dict]) -> tuple[list[float], list[float]]:
        """Return (floor, ceiling); always floor <= mean <= ceiling elementwise."""
        if not rows:
            return [], []
        mid = np.array(self.predict_rows(position, rows), float)
        lo_m, hi_m = self._lo.get(position), self._hi.get(position)
        if lo_m is None or hi_m is None:
            return list(mid - 2.0), list(mid + 2.0)
        x = self._x(rows)
        lo = np.minimum(lo_m.predict(x), mid)
        hi = np.maximum(hi_m.predict(x), mid)
        return [float(v) for v in lo], [float(v) for v in hi]

    def save(self, directory) -> None:
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({
            "version": self.version, "global_mean": self._global_mean,
            "feature_names": self.feature_names, "positions": self.positions(),
            "pos_means": self._pos_means, "feature_medians": self._medians,
        }))
        for pos in self.positions():
            (d / f"{pos}.mean.json").write_text(self._mean[pos].to_json())
            (d / f"{pos}.lo.json").write_text(self._lo[pos].to_json())
            (d / f"{pos}.hi.json").write_text(self._hi[pos].to_json())

    @classmethod
    def load(cls, directory) -> AdvancedXP:
        d = Path(directory)
        meta = json.loads((d / "meta.json").read_text())
        positions = meta["positions"]

        def rd(pos: str, kind: str) -> GBRT:
            return GBRT.from_json((d / f"{pos}.{kind}.json").read_text())

        return cls(
            {p: rd(p, "mean") for p in positions},
            {p: rd(p, "lo") for p in positions},
            {p: rd(p, "hi") for p in positions},
            meta["global_mean"], meta.get("pos_means", {}), meta["version"],
            meta.get("feature_medians", {}),
        )


def train_advanced(frame: pd.DataFrame, *, min_rows: int = _MIN_ROWS,
                   **gbrt_kw) -> AdvancedXP:
    kw = dict(n_estimators=250, learning_rate=0.05, max_depth=3, min_leaf=25,
              subsample=0.8, seed=0)
    kw.update(gbrt_kw)
    if frame.empty:
        return AdvancedXP({}, {}, {}, 0.0, {})
    mean_m, lo_m, hi_m, medians = {}, {}, {}, {}
    for pos, g in frame.groupby("position"):
        if len(g) < min_rows:
            continue
        x = g[FEATURE_NAMES_ADV].to_numpy(float)
        y = g["target"].to_numpy(float)
        mean_m[pos] = GBRT.fit(x, y, loss="l2", **kw)
        lo_m[pos] = GBRT.fit(x, y, loss="quantile", alpha=_LO, **kw)
        hi_m[pos] = GBRT.fit(x, y, loss="quantile", alpha=_HI, **kw)
        medians[str(pos)] = [float(v) for v in g[FEATURE_NAMES_ADV].median().tolist()]
    pos_means = {str(k): float(v)
                 for k, v in frame.groupby("position")["target"].mean().items()}
    return AdvancedXP(mean_m, lo_m, hi_m, float(frame["target"].mean()), pos_means,
                      feature_medians=medians)
