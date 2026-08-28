"""Pure live-scoring math — no DB, no network.

`project_bonus`  : one fixture's {player_id: bps} -> {player_id: 0|1|2|3}
`build_live_rows`: an event/{gw}/live payload -> player_gw_live row dicts
"""
from __future__ import annotations

from typing import Any

__all__ = ["project_bonus", "build_live_rows"]

_SYNTHETIC_FIXTURE = -1


def project_bonus(bps_by_player: dict[int, int]) -> dict[int, int]:
    """Provisional FPL bonus, by *rank position* (standard competition ranking).
    Rank 0 (highest BPS) -> 3, rank 1 -> 2, rank 2 -> 1, below that -> 0. Tied
    players share a rank, so a tie for a place consumes the place(s) below it
    (e.g. BPS 30, 30, 25 -> 3, 3, 1). Only positive BPS is eligible."""
    if not bps_by_player:
        return {}
    positives = [b for b in bps_by_player.values() if b > 0]
    by_rank = {0: 3, 1: 2, 2: 1}
    award: dict[int, int] = {}
    for pid, b in bps_by_player.items():
        if b <= 0:
            award[pid] = 0
            continue
        rank = sum(1 for v in positives if v > b)
        award[pid] = by_rank.get(rank, 0)
    return award


def _bps_from_explain(entry: dict[str, Any]) -> int:
    for item in entry.get("stats", []):
        if item.get("identifier") == "bps":
            return int(item.get("value", 0))
    return 0


def build_live_rows(gameweek_id: int, payload: dict[str, Any]) -> list[dict]:
    by_fixture: dict[int, dict[int, int]] = {}
    meta: dict[int, tuple[int, int, int]] = {}  # pid -> (minutes, live_points, bps_total)

    for el in payload.get("elements", []):
        pid = el["id"]
        s = el.get("stats", {})
        minutes = int(s.get("minutes", 0))
        bps_total = int(s.get("bps", 0))
        explain = el.get("explain") or []
        if minutes == 0 and bps_total == 0 and not explain:
            continue
        meta[pid] = (minutes, int(s.get("total_points", 0)), bps_total)
        if explain:
            for e in explain:
                by_fixture.setdefault(int(e["fixture"]), {})[pid] = _bps_from_explain(e)
        else:
            by_fixture.setdefault(_SYNTHETIC_FIXTURE, {})[pid] = bps_total

    awards: dict[int, int] = {}
    for bps_map in by_fixture.values():
        for pid, bonus in project_bonus(bps_map).items():
            awards[pid] = awards.get(pid, 0) + bonus

    rows: list[dict] = []
    for pid, (minutes, live_points, bps_total) in meta.items():
        pb = awards.get(pid, 0)
        rows.append({
            "player_id": pid,
            "gameweek_id": gameweek_id,
            "minutes": minutes,
            "live_points": live_points,
            "bps": bps_total,
            "projected_bonus": pb,
            "total_points": live_points + pb,
        })
    return rows
