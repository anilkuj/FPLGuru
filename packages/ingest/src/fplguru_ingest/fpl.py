from datetime import datetime
from typing import Any

from fplguru_core.constants import POSITION_BY_ELEMENT_TYPE


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_teams(bootstrap: dict[str, Any]) -> list[dict]:
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "short_name": t["short_name"],
            "strength_overall_home": t["strength_overall_home"],
            "strength_overall_away": t["strength_overall_away"],
            "strength_attack_home": t["strength_attack_home"],
            "strength_attack_away": t["strength_attack_away"],
            "strength_defence_home": t["strength_defence_home"],
            "strength_defence_away": t["strength_defence_away"],
        }
        for t in bootstrap["teams"]
    ]


def normalize_gameweeks(bootstrap: dict[str, Any]) -> list[dict]:
    return [
        {
            "id": e["id"],
            "name": e["name"],
            "deadline_time": _parse_dt(e["deadline_time"]),
            "is_current": bool(e["is_current"]),
            "is_next": bool(e["is_next"]),
            "finished": bool(e["finished"]),
            "average_entry_score": e.get("average_entry_score"),
        }
        for e in bootstrap["events"]
    ]


def normalize_players(bootstrap: dict[str, Any]) -> list[dict]:
    return [
        {
            "id": el["id"],
            "team_id": el["team"],
            "first_name": el["first_name"],
            "second_name": el["second_name"],
            "web_name": el["web_name"],
            "position": POSITION_BY_ELEMENT_TYPE[el["element_type"]],
            "now_cost": el["now_cost"],
            "status": el["status"],
            "chance_of_playing_next_round": el.get("chance_of_playing_next_round"),
            "news": el.get("news", ""),
            "selected_by_percent": float(el["selected_by_percent"]),
            "total_points": el["total_points"],
        }
        for el in bootstrap["elements"]
    ]


def normalize_fixtures(fixtures: list[dict[str, Any]]) -> list[dict]:
    return [
        {
            "id": f["id"],
            "gameweek_id": f["event"],
            "kickoff_time": _parse_dt(f.get("kickoff_time")),
            "home_team_id": f["team_h"],
            "away_team_id": f["team_a"],
            "home_difficulty": f["team_h_difficulty"],
            "away_difficulty": f["team_a_difficulty"],
            "finished": bool(f["finished"]),
            "home_score": f.get("team_h_score"),
            "away_score": f.get("team_a_score"),
        }
        for f in fixtures
    ]
