"""Pure head-to-head squad comparison (no DB, no network)."""
from __future__ import annotations

from typing import Any

from fplguru_optimize import best_xi

__all__ = ["compare_squads", "template_strategy"]


def _brief(p: dict) -> dict:
    return {"player_id": p["player_id"], "web_name": p.get("web_name", ""),
            "position": p["position"], "xp": round(float(p.get("xp", 0.0)), 2)}


def template_strategy(margin: float, *, same_captain: bool,
                      their_diffs: list[dict]) -> str:
    top = max(their_diffs, key=lambda p: p["xp"], default=None)
    threat = (
        f" Watch {top['web_name']} ({top['xp']} xP) — their best player you don't own."
        if top and top["xp"] > 3 else ""
    )
    if margin >= 3:
        return (f"You're ahead by ~{margin:.1f} projected pts. Play the percentages: match "
                f"their captain and avoid needless risk.{threat}")
    if margin <= -3:
        return (f"You're behind by ~{abs(margin):.1f} projected pts. Consider a differential "
                f"captain or an aggressive transfer to create swing.{threat}")
    cap = ("Your captains match — the bench and differentials decide this one."
           if same_captain else "Close on paper; your captain call is the likely swing.")
    return f"Roughly level (within {abs(margin):.1f} pts). {cap}{threat}"


def compare_squads(mine: list[dict[str, Any]], theirs: list[dict[str, Any]], *,
                   horizon: int) -> dict:
    my_xi = best_xi(mine, key="xp")
    their_xi = best_xi(theirs, key="xp")
    my_ids = {p["player_id"] for p in mine}
    their_ids = {p["player_id"] for p in theirs}
    your_diffs = sorted((_brief(p) for p in mine if p["player_id"] not in their_ids),
                        key=lambda p: -p["xp"])
    their_diffs = sorted((_brief(p) for p in theirs if p["player_id"] not in my_ids),
                         key=lambda p: -p["xp"])
    margin = round(my_xi["total"] - their_xi["total"], 2)
    same_cap = bool(my_xi["captain"] and their_xi["captain"]
                    and my_xi["captain"]["player_id"] == their_xi["captain"]["player_id"])
    return {
        "horizon": horizon,
        "your_xi_total": my_xi["total"],
        "their_xi_total": their_xi["total"],
        "margin": margin,
        "your_captain": _brief(my_xi["captain"]) if my_xi["captain"] else None,
        "their_captain": _brief(their_xi["captain"]) if their_xi["captain"] else None,
        "same_captain": same_cap,
        "shared_count": len(my_ids & their_ids),
        "your_differentials": your_diffs,
        "their_differentials": their_diffs,
        "strategy": template_strategy(margin, same_captain=same_cap,
                                      their_diffs=their_diffs),
    }
