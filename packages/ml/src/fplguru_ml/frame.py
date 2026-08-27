"""Historical vaastav rows -> leak-free training frame (features + target).

Deterministic rules:
- an "appearance" is a row with minutes > 0
- a player-GW row needs >= 3 prior appearances to be kept in the frame
- 5-window means average over whatever is available (min 1)
- opp_conceded_to_pos_5: recency-weighted mean of total_points the opponent team
  conceded to this player's position group, that season, using only prior GWs
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from fplguru_ml.features import FEATURE_NAMES, wmean

_POS = {"GK", "DEF", "MID", "FWD"}


def build_training_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df = df[df["position"].isin(_POS)].copy()
    df["clean_sheet"] = df["clean_sheet"].astype(bool)
    df = df.sort_values(["season", "player_name", "gameweek"]).reset_index(drop=True)

    # opponent points-conceded-to-position, leak-free, per season
    keys = list(zip(df["season"], df["opponent_team_id"], df["position"], strict=False))
    concede: dict = {}
    opp_feat = []
    for key, tp in zip(keys, df["total_points"], strict=False):
        hist = concede.get(key, [])
        opp_feat.append(wmean([float(x) for x in hist[-5:]], 5) if hist else np.nan)
        concede.setdefault(key, []).append(tp)
    df["opp_conceded_to_pos_5"] = opp_feat

    out = []
    for (_, _), g in df.groupby(["season", "player_name"], sort=False):
        g = g.sort_values("gameweek")
        app_mask = g["minutes"] > 0
        pts = g.loc[app_mask, "total_points"].tolist()
        mins = g.loc[app_mask, "minutes"].tolist()
        gls = g.loc[app_mask, "goals"].tolist()
        ast = g.loc[app_mask, "assists"].tolist()
        app_index = set(g.index[app_mask])
        seen = 0
        for r in g.itertuples():
            prior_pts, prior_mins = pts[:seen], mins[:seen]
            prior_gls, prior_ast = gls[:seen], ast[:seen]
            if r.Index in app_index:
                seen += 1
            if len(prior_pts) < 3:
                continue
            starts = [1.0 if m >= 60 else 0.0 for m in prior_mins[-5:]]
            out.append({
                "season": r.season, "player_name": r.player_name, "position": r.position,
                "gameweek": r.gameweek,
                "form_points_3": wmean(prior_pts, 3),
                "form_points_5": wmean(prior_pts, 5),
                "form_minutes_3": float(np.mean(prior_mins[-3:])),
                "starts_rate_5": float(np.mean(starts)) if starts else 0.0,
                "form_goals_5": float(np.mean(prior_gls[-5:])) if prior_gls else 0.0,
                "form_assists_5": float(np.mean(prior_ast[-5:])) if prior_ast else 0.0,
                "was_home": 1.0 if bool(r.was_home) else 0.0,
                "value": float(r.value),
                "opp_conceded_to_pos_5": float(r.opp_conceded_to_pos_5)
                    if not pd.isna(r.opp_conceded_to_pos_5) else 0.0,
                "target": float(r.total_points),
            })
    frame = pd.DataFrame(out)
    for c in FEATURE_NAMES:
        if c not in frame.columns:
            frame[c] = 0.0
    return frame
