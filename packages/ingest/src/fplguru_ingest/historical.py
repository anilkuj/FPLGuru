from pathlib import Path

import pandas as pd


def normalize_merged_gw(csv_path: str | Path, season: str) -> list[dict]:
    df = pd.read_csv(csv_path)
    out: list[dict] = []
    for r in df.itertuples(index=False):
        out.append(
            {
                "season": season,
                "player_name": r.name,
                "position": r.position,
                "team": r.team,
                "gameweek": int(r.GW),
                "minutes": int(r.minutes),
                "goals": int(r.goals_scored),
                "assists": int(r.assists),
                "clean_sheet": int(r.clean_sheets) > 0,
                "total_points": int(r.total_points),
                "xg": float(r.expected_goals),
                "xa": float(r.expected_assists),
                "was_home": bool(r.was_home),
                "opponent_team_id": int(r.opponent_team),
                "value": int(r.value),
            }
        )
    return out
