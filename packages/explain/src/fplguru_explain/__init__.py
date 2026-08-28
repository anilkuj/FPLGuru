"""Pure helpers: turn Advanced-xP drivers into an LLM prompt or a template string."""
from __future__ import annotations

from typing import Any

__all__ = ["DRIVER_PHRASES", "explanation_prompt", "template_explanation"]

# keys are a subset of fplguru_ml.features.FEATURE_NAMES_ADV
DRIVER_PHRASES: dict[str, str] = {
    "form_points_3": "very recent scoring",
    "form_points_5": "recent scoring",
    "form_minutes_3": "recent minutes",
    "starts_rate_5": "starts security",
    "form_goals_5": "recent goals",
    "form_assists_5": "recent assists",
    "was_home": "home advantage",
    "value": "price bracket",
    "opp_conceded_to_pos_5": "how much upcoming opponents concede to this position",
    "form_xg_5": "recent xG",
    "form_xa_5": "recent xA",
    "xg_overperf_5": "finishing vs xG",
    "form_xgc_5": "defensive workload (xGC)",
    "form_ict_5": "overall involvement (ICT)",
}


def _phrase(name: str) -> str:
    return DRIVER_PHRASES.get(name, name.replace("_", " "))


def _driver_lines(drivers: list[tuple[str, float]]) -> str:
    return "; ".join(
        f"{_phrase(n)} {'raises' if d >= 0 else 'lowers'} the projection"
        for n, d in drivers
    ) or "no single dominant factor"


def template_explanation(player: dict[str, Any], *, xp: float, floor: float,
                         ceiling: float, drivers: list[tuple[str, float]],
                         horizon: int) -> str:
    return (
        f"{player['web_name']} ({player['team_short']}, {player['position']}) projects "
        f"{xp:.1f} pts over the next {horizon} GW(s) (range {floor:.1f}-{ceiling:.1f}). "
        f"Main factors: {_driver_lines(drivers)}."
    )


def explanation_prompt(player: dict[str, Any], fixtures: list[dict[str, Any]],
                       drivers: list[tuple[str, float]], *, xp: float, floor: float,
                       ceiling: float, horizon: int) -> str:
    fx = ", ".join(
        f"{f['opponent_short']} ({'H' if f['was_home'] else 'A'}, FDR {f['difficulty']})"
        for f in fixtures[:horizon]
    ) or "unknown"
    dl = "; ".join(
        f"{_phrase(n)} ({'+' if d >= 0 else '-'})" for n, d in drivers
    ) or "none"
    return (
        f"You are an FPL analyst. In ONE or TWO plain sentences, explain the projected points for "
        f"{player['web_name']} ({player['team_short']}, {player['position']}): {xp:.1f} pts over "
        f"the next {horizon} gameweek(s), likely range {floor:.1f}-{ceiling:.1f}. "
        f"Upcoming fixtures: {fx}. The model says these factors move it "
        f"(+ raises, - lowers): {dl}. No preamble, no bullet points, no numbered list."
    )
