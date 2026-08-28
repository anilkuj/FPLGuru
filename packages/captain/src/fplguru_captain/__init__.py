"""Pure captain-pick ranking + LLM prompt building."""
from __future__ import annotations

from typing import Any

__all__ = ["rank_captains", "rationale_prompt"]


def _ranked(players: list[dict[str, Any]], top: int) -> list[dict]:
    ordered = sorted(players, key=lambda p: (-float(p.get("xp", 0.0)), p["player_id"]))
    return [
        {"player_id": p["player_id"], "web_name": p["web_name"],
         "position": p["position"], "team_short": p.get("team_short", ""),
         "xp": round(float(p.get("xp", 0.0)), 2)}
        for p in ordered[:top]
    ]


def rank_captains(squad: list[dict[str, Any]], all_players: list[dict[str, Any]], *,
                  top: int = 5) -> dict:
    return {
        "constrained": _ranked([p for p in squad if p.get("in_xi")], top),
        "unconstrained": _ranked(all_players, top),
    }


def rationale_prompt(pick: dict[str, Any], alternatives: list[dict[str, Any]], *,
                     kind: str, horizon: int) -> str:
    alt = ", ".join(f"{a['web_name']} ({a['xp']} xP)" for a in alternatives[:3]) or "none"
    scope = "your starting XI" if kind == "constrained" else "all players"
    return (
        f"You are an FPL analyst. In ONE or TWO plain sentences, explain why "
        f"{pick['web_name']} ({pick['team_short']}, {pick['position']}) is the top captain pick "
        f"from {scope} for the next {horizon} gameweek(s), given a projected {pick['xp']} points. "
        f"Nearest alternatives: {alt}. No preamble, no bullet points."
    )
