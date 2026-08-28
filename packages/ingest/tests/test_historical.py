from pathlib import Path

from fplguru_ingest.historical import normalize_merged_gw

CSV = Path(__file__).parent / "fixtures" / "merged_gw_sample.csv"


def test_normalize_merged_gw_rows():
    rows = normalize_merged_gw(CSV, season="2024-25")
    assert len(rows) == 2
    assert rows[0] == {
        "season": "2024-25",
        "player_name": "Bukayo Saka",
        "position": "MID",
        "team": "Arsenal",
        "gameweek": 1,
        "minutes": 90,
        "goals": 1,
        "assists": 0,
        "clean_sheet": True,
        "total_points": 9,
        "xg": 0.42,
        "xa": 0.31,
        "xgc": 0.55,
        "goals_conceded": 0,
        "ict": 12.3,
        "was_home": True,
        "opponent_team_id": 15,
        "value": 100,
    }
    assert rows[1]["clean_sheet"] is False
    assert rows[1]["was_home"] is False
