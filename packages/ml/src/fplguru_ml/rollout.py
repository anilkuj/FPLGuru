from __future__ import annotations

from dataclasses import dataclass

_BASE_SPREAD = 4.0
_GROWTH = 0.35


@dataclass
class GwPrediction:
    horizon_gw: int
    xp: float
    floor: float
    ceiling: float


@dataclass
class HorizonPrediction:
    position: str
    per_gw: list[GwPrediction]

    @property
    def cumulative(self) -> float:
        return float(sum(p.xp for p in self.per_gw))


def band_halfwidth(horizon_gw: int) -> float:
    """Half-width of the xP confidence band at a given horizon (GW 1 = _BASE_SPREAD/2)."""
    return _BASE_SPREAD * (1.0 + _GROWTH * (horizon_gw - 1)) / 2.0


def project_horizon(position: str, per_gw_feature_rows: list[dict], model) -> HorizonPrediction:
    """Basic tier: each future GW predicted independently from the caller-supplied
    feature row for that GW; confidence band widens linearly with horizon."""
    xps = model.predict_rows(position, per_gw_feature_rows)
    out = []
    for i, xp in enumerate(xps, start=1):
        half = band_halfwidth(i)
        out.append(GwPrediction(i, float(xp), float(xp - half), float(xp + half)))
    return HorizonPrediction(position, out)
