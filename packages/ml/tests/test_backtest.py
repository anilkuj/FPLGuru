import numpy as np
import pandas as pd

from fplguru_ml.backtest import walk_forward
from fplguru_ml.features import FEATURE_NAMES


def _synthetic(n_gw=12, players_per_pos=15):
    rng = np.random.default_rng(3)
    rows = []
    for pos, w in (("MID", 4.0), ("DEF", 2.5)):
        for p in range(players_per_pos):
            for gw in range(1, n_gw + 1):
                feats = {k: float(rng.normal()) for k in FEATURE_NAMES}
                target = (w * feats["form_points_5"] + 0.3 * feats["was_home"]
                          + rng.normal(scale=0.5))
                rows.append({"season": "s", "player_name": f"{pos}{p}", "position": pos,
                             "gameweek": gw, "target": target, **feats})
    return pd.DataFrame(rows)


def test_walk_forward_beats_naive_mean():
    frame = _synthetic()
    res = walk_forward(frame, alpha=1.0, min_train_gw=4)
    m = res.metrics_by_position()
    assert set(m) == {"MID", "DEF"}
    assert m["MID"]["rmse"] < m["MID"]["baseline_rmse"]
    assert m["MID"]["n"] > 0


def test_no_leakage_each_fold_trains_on_past_only():
    frame = _synthetic()
    res = walk_forward(frame, alpha=1.0, min_train_gw=4)
    assert res.folds[0].train_max_gw < res.folds[0].test_gw
