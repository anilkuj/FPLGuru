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
            "transfers_in_event": el.get("transfers_in_event", 0),
            "transfers_out_event": el.get("transfers_out_event", 0),
            "cost_change_event": el.get("cost_change_event", 0),
            "form": float(el.get("form") or 0.0),
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
            "started": bool(f.get("started", False)),
            "finished_provisional": bool(f.get("finished_provisional", False)),
            "minutes": int(f.get("minutes", 0) or 0),
        }
        for f in fixtures
    ]


def normalize_entry(payload: dict[str, Any]) -> dict:
    first = payload.get("player_first_name", "")
    last = payload.get("player_last_name", "")
    leagues = [
        {"league_id": lg["id"], "league_name": lg.get("name", ""),
         "entry_rank": lg.get("entry_rank"), "entry_last_rank": lg.get("entry_last_rank")}
        for lg in payload.get("leagues", {}).get("classic", [])
    ]
    return {
        "fpl_entry_id": payload["id"],
        "manager_name": f"{first} {last}".strip(),
        "started_event": payload.get("started_event"),
        "favourite_team_id": payload.get("favourite_team"),
        "leagues": leagues,
    }


def normalize_league_standings(league_id: int, payload: dict[str, Any]) -> dict:
    st = payload.get("standings", {})
    rows = [
        {
            "league_id": league_id,
            "entry_id": r["entry"],
            "entry_name": r.get("entry_name", ""),
            "player_name": r.get("player_name", ""),
            "rank": r["rank"],
            "last_rank": r.get("last_rank"),
            "total": r.get("total", 0),
            "event_total": r.get("event_total", 0),
        }
        for r in st.get("results", [])
    ]
    return {
        "league_name": payload.get("league", {}).get("name", ""),
        "has_next": bool(st.get("has_next", False)),
        "rows": rows,
    }


def normalize_entry_history(payload: dict[str, Any]) -> list[dict]:
    return [
        {
            "gameweek_id": r["event"],
            "points": r["points"],
            "total_points": r["total_points"],
            "overall_rank": r.get("overall_rank"),
            "bank": r["bank"],
            "team_value": r["value"],
            "transfers": r["event_transfers"],
            "transfer_cost": r["event_transfers_cost"],
            "points_on_bench": r["points_on_bench"],
        }
        for r in payload.get("current", [])
    ]


def normalize_entry_picks(gameweek_id: int, payload: dict[str, Any]) -> list[dict]:
    return [
        {
            "gameweek_id": gameweek_id,
            "player_id": p["element"],
            "slot": p["position"],
            "multiplier": p["multiplier"],
            "is_captain": bool(p["is_captain"]),
            "is_vice": bool(p["is_vice_captain"]),
        }
        for p in payload.get("picks", [])
    ]


def normalize_event_live(gameweek_id: int, payload: dict[str, Any]) -> list[dict]:
    out = []
    for el in payload["elements"]:
        s = el["stats"]
        out.append(
            {
                "player_id": el["id"],
                "gameweek_id": gameweek_id,
                "minutes": s["minutes"],
                "total_points": s["total_points"],
                "goals": s["goals_scored"],
                "assists": s["assists"],
                "clean_sheets": s["clean_sheets"],
                "goals_conceded": s["goals_conceded"],
                "bonus": s["bonus"],
            }
        )
    return out
