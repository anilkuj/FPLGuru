"""Pure alert generation + priority scoring — no DB, no network."""
from __future__ import annotations

from typing import Any

__all__ = ["score_alert", "availability_alerts", "dgw_bgw_alerts"]

_BASE = {"availability": 60, "bgw": 45, "dgw": 40}
_HARD_OUT = {"i", "s", "u"}

_STATUS_LABEL = {
    "a": "available", "d": "doubtful", "i": "injured",
    "s": "suspended", "u": "unavailable", "n": "not in squad",
}


def score_alert(alert: dict[str, Any], *, in_xi: bool, is_captain: bool,
                before_deadline: bool) -> int:
    score = _BASE.get(alert["type"], 20)
    if is_captain:
        score += 25
    elif in_xi:
        score += 15
    if alert["type"] == "availability" and alert.get("payload", {}).get("status") in _HARD_OUT:
        score += 15
    if before_deadline:
        score += 10
    return max(0, min(100, score))


def availability_alerts(picks: list[dict[str, Any]], *, gameweek_id: int) -> list[dict]:
    out: list[dict] = []
    for p in picks:
        status = p.get("status", "a")
        chance = p.get("chance_of_playing_next_round")
        if status == "a" and (chance is None or chance >= 100):
            continue
        chance_key = "na" if chance is None else str(chance)
        news = (p.get("news") or "").strip()
        label = _STATUS_LABEL.get(status, status)
        detail = news or (
            f"Chance of playing next round: {chance}%." if chance is not None
            else "Status changed."
        )
        out.append({
            "type": "availability",
            "dedup_key": f"avail:{p['player_id']}:{status}:{chance_key}",
            "gameweek_id": gameweek_id,
            "player_id": p["player_id"],
            "title": f"{p['web_name']}: {label}",
            "body": detail,
            "payload": {
                "status": status,
                "chance": chance,
                "news": news,
                "in_xi": p.get("multiplier", 0) > 0,
                "is_captain": bool(p.get("is_captain")),
                "is_vice": bool(p.get("is_vice")),
            },
        })
    return out


def dgw_bgw_alerts(owned_team_ids: set[int], fixture_counts: dict[int, int],
                   names_by_team: dict[int, list[str]], *, gameweek_id: int) -> list[dict]:
    out: list[dict] = []
    for team_id in sorted(owned_team_ids):
        n = fixture_counts.get(team_id, 0)   # absent = no fixture that GW = blank
        names = names_by_team.get(team_id, [])
        if n == 0:
            kind, label = "bgw", "Blank gameweek"
        elif n >= 2:
            kind, label = "dgw", "Double gameweek"
        else:
            continue
        who = ", ".join(names) if names else "your player(s)"
        out.append({
            "type": kind,
            "dedup_key": f"{kind}:{team_id}:{gameweek_id}",
            "gameweek_id": gameweek_id,
            "player_id": None,
            "title": f"{label} — GW{gameweek_id}",
            "body": f"{label} for {who} ({n} fixture{'s' if n != 1 else ''}).",
            "payload": {"team_id": team_id, "fixtures": n, "player_names": names},
        })
    return out
