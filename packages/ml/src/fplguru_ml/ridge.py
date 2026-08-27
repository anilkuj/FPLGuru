from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np


@dataclass
class RidgeModel:
    feature_names: list[str]
    mean_: np.ndarray
    std_: np.ndarray
    coef_: np.ndarray
    intercept_: float
    alpha: float

    @classmethod
    def fit(cls, X, y, *, feature_names: list[str], alpha: float) -> RidgeModel:
        X = np.asarray(X, float)
        y = np.asarray(y, float)
        mean = X.mean(axis=0)
        std = X.std(axis=0)
        std[std == 0] = 1.0
        xs = (X - mean) / std
        d = xs.shape[1]
        a = xs.T @ xs + alpha * np.eye(d)
        b = xs.T @ (y - y.mean())
        coef = np.linalg.solve(a, b)
        return cls(list(feature_names), mean, std, coef, float(y.mean()), float(alpha))

    def predict(self, X) -> np.ndarray:
        X = np.asarray(X, float)
        if X.shape[1] != len(self.feature_names):
            raise ValueError(f"expected {len(self.feature_names)} features, got {X.shape[1]}")
        xs = (X - self.mean_) / self.std_
        return xs @ self.coef_ + self.intercept_

    def to_json(self) -> str:
        return json.dumps({
            "feature_names": self.feature_names,
            "mean": self.mean_.tolist(), "std": self.std_.tolist(),
            "coef": self.coef_.tolist(), "intercept": self.intercept_, "alpha": self.alpha,
        })

    @classmethod
    def from_json(cls, s: str) -> RidgeModel:
        d = json.loads(s)
        return cls(d["feature_names"], np.array(d["mean"]), np.array(d["std"]),
                   np.array(d["coef"]), float(d["intercept"]), float(d["alpha"]))
