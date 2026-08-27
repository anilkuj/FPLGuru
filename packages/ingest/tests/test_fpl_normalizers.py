import json
from pathlib import Path

from fplguru_ingest.fpl import (
    normalize_event_live,
    normalize_fixtures,
    normalize_gameweeks,
    normalize_players,
    normalize_teams,
)

FIX = Path(__file__).parent / "fixtures"
BOOTSTRAP = json.loads((FIX / "bootstrap_sample.json").read_text())
FIXTURES = json.loads((FIX / "fixtures_sample.json").read_text())


def test_normalize_teams():
    rows = normalize_teams(BOOTSTRAP)
    assert rows == [{
        "id": 1, "name": "Arsenal", "short_name": "ARS",
        "strength_overall_home": 1300, "strength_overall_away": 1310,
        "strength_attack_home": 1350, "strength_attack_away": 1340,
        "strength_defence_home": 1250, "strength_defence_away": 1260,
    }]


def test_normalize_gameweeks_parses_utc_deadline():
    rows = normalize_gameweeks(BOOTSTRAP)
    assert rows[0]["id"] == 1
    assert rows[0]["deadline_time"].tzinfo is not None
    assert rows[0]["deadline_time"].isoformat() == "2025-08-15T17:30:00+00:00"
    assert rows[0]["is_next"] is True


def test_normalize_players_maps_position_and_percent():
    row = normalize_players(BOOTSTRAP)[0]
    assert row["position"] == "MID"
    assert row["team_id"] == 1
    assert row["selected_by_percent"] == 42.1
    assert row["now_cost"] == 100


def test_normalize_fixtures_handles_null_event_and_kickoff():
    rows = normalize_fixtures(FIXTURES)
    assert rows[0]["gameweek_id"] == 1
    assert rows[0]["kickoff_time"].isoformat() == "2025-08-16T14:00:00+00:00"
    assert rows[1]["gameweek_id"] is None
    assert rows[1]["kickoff_time"] is None
    assert rows[1]["home_difficulty"] == 4


EVENT_LIVE = json.loads((FIX / "event_live_sample.json").read_text())


def test_normalize_event_live_maps_stats():
    rows = normalize_event_live(7, EVENT_LIVE)
    assert rows[0] == {
        "player_id": 11, "gameweek_id": 7, "minutes": 90, "total_points": 9,
        "goals": 1, "assists": 0, "clean_sheets": 1, "goals_conceded": 0, "bonus": 2,
    }
    assert rows[1]["minutes"] == 0
