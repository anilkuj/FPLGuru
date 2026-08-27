from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fplguru_ml.features import FEATURE_NAMES
from fplguru_ml.ridge import RidgeModel

VERSION = "basic-v1"


class BasicXP:
    def __init__(self, models: dict[str, RidgeModel], global_mean: float,
                 version: str = VERSION) -> None:
        self._models = models
        self._global_mean = float(global_mean)
        self.version = version
        self.feature_names = list(FEATURE_NAMES)

    def positions(self) -> list[str]:
        return sorted(self._models)

    def predict_rows(self, position: str, rows: list[dict]) -> list[float]:
        if not rows:
            return []
        model = self._models.get(position)
        if model is None:
            return [self._global_mean] * len(rows)
        x = np.array([[float(r[k]) for k in self.feature_names] for r in rows], float)
        return [float(v) for v in model.predict(x)]

    def save(self, directory) -> None:
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps({
            "version": self.version, "global_mean": self._global_mean,
            "feature_names": self.feature_names, "positions": self.positions(),
        }))
        for pos, model in self._models.items():
            (d / f"{pos}.json").write_text(model.to_json())

    @classmethod
    def load(cls, directory) -> BasicXP:
        d = Path(directory)
        meta = json.loads((d / "meta.json").read_text())
        models = {pos: RidgeModel.from_json((d / f"{pos}.json").read_text())
                  for pos in meta["positions"]}
        return cls(models, meta["global_mean"], meta["version"])


def train_basic(frame: pd.DataFrame, *, alpha: float = 1.0) -> BasicXP:
    if frame.empty:
        return BasicXP({}, 0.0)
    models: dict[str, RidgeModel] = {}
    for pos, g in frame.groupby("position"):
        if len(g) < len(FEATURE_NAMES) + 1:
            continue
        x = g[FEATURE_NAMES].to_numpy(float)
        y = g["target"].to_numpy(float)
        models[pos] = RidgeModel.fit(x, y, feature_names=FEATURE_NAMES, alpha=alpha)
    return BasicXP(models, float(frame["target"].mean()))
