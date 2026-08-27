from __future__ import annotations

import numpy as np

FEATURE_NAMES = [
    "form_points_3", "form_points_5", "form_minutes_3", "starts_rate_5",
    "form_goals_5", "form_assists_5", "was_home", "value", "opp_conceded_to_pos_5",
]


def wmean(vals, n: int) -> float:
    """Recency-weighted mean of the last `n` values (weights 1..len)."""
    v = list(vals)[-n:]
    if not v:
        return float("nan")
    w = np.arange(1, len(v) + 1, dtype=float)
    return float(np.dot(v, w) / w.sum())


def feature_row_from_history(
    history,
    *,
    was_home: bool,
    value: float,
    opp_conceded_to_pos_5: float,
) -> dict | None:
    """`history` = list of prior *appearances* (minutes > 0), oldest-first, each a
    dict with total_points / minutes / goals / assists. Returns None if < 3 appearances.
    """
    if len(history) < 3:
        return None
    pts = [float(h["total_points"]) for h in history]
    mins = [float(h["minutes"]) for h in history]
    gls = [float(h["goals"]) for h in history]
    ast = [float(h["assists"]) for h in history]
    starts = [1.0 if m >= 60 else 0.0 for m in mins[-5:]]
    return {
        "form_points_3": wmean(pts, 3),
        "form_points_5": wmean(pts, 5),
        "form_minutes_3": float(np.mean(mins[-3:])),
        "starts_rate_5": float(np.mean(starts)) if starts else 0.0,
        "form_goals_5": float(np.mean(gls[-5:])),
        "form_assists_5": float(np.mean(ast[-5:])),
        "was_home": 1.0 if was_home else 0.0,
        "value": float(value),
        "opp_conceded_to_pos_5": float(opp_conceded_to_pos_5),
    }
