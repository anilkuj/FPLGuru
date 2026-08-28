"""Pure squad optimiser: best XI, transfer suggestions, chip-timing hints.

No DB, no network. Every ``xp`` value a caller passes is expected to already be
cumulative over the caller's chosen horizon.
"""
from __future__ import annotations

from typing import Any

__all__ = ["best_xi", "suggest_transfers", "chip_hints", "SQUAD_SHAPE", "HIT_COST"]

# GK / DEF / MID / FWD squad quotas (15 total); XI outfield splits (DEF, MID, FWD), GK always 1
SQUAD_SHAPE = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
_FORMATIONS = [(3, 4, 3), (3, 5, 2), (4, 4, 2), (4, 3, 3), (4, 5, 1), (5, 4, 1), (5, 3, 2)]
_POS_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}
HIT_COST = 4.0


def _by_pos(players: list[dict]) -> dict[str, list[dict]]:
    d: dict[str, list[dict]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for p in players:
        if p["position"] in d:
            d[p["position"]].append(p)
    for pos in d:
        d[pos].sort(key=lambda p: (p.get("xp", 0.0), -p["player_id"]), reverse=True)
    return d


def _best_xi_ids(players: list[dict], key: str) -> tuple[list[dict], float]:
    bp = _by_pos(players)
    if not bp["GK"]:
        return [], 0.0
    gk = bp["GK"][:1]
    best: tuple[list[dict], float] | None = None
    for d, m, f in _FORMATIONS:
        if len(bp["DEF"]) < d or len(bp["MID"]) < m or len(bp["FWD"]) < f:
            continue
        xi = gk + bp["DEF"][:d] + bp["MID"][:m] + bp["FWD"][:f]
        score = sum(p.get(key, 0.0) for p in xi)
        if best is None or score > best[1]:
            best = (xi, score)
    return best if best else ([], 0.0)


def best_xi(squad: list[dict[str, Any]], *, key: str = "xp") -> dict:
    """Highest-`key` legal XI from a 15-man squad, plus bench order, captain, vice."""
    xi, total = _best_xi_ids(squad, key)
    xi_ids = {p["player_id"] for p in xi}
    bench = [p for p in squad if p["player_id"] not in xi_ids]
    bench.sort(key=lambda p: (p["position"] != "GK", -p.get(key, 0.0), p["player_id"]))
    xi_sorted = sorted(xi, key=lambda p: (_POS_ORDER[p["position"]], -p.get(key, 0.0)))
    ranked = sorted(xi, key=lambda p: (-p.get(key, 0.0), p["player_id"]))
    n = {"DEF": 0, "MID": 0, "FWD": 0}
    for p in xi:
        if p["position"] in n:
            n[p["position"]] += 1
    return {
        "formation": f"{n['DEF']}-{n['MID']}-{n['FWD']}",
        "total": round(total, 2),
        "xi": xi_sorted,
        "bench": bench,
        "captain": ranked[0] if ranked else None,
        "vice": ranked[1] if len(ranked) > 1 else None,
    }


def _club_counts(squad: list[dict]) -> dict[int, int]:
    c: dict[int, int] = {}
    for p in squad:
        c[p["team_id"]] = c.get(p["team_id"], 0) + 1
    return c


def _apply(squad: list[dict], out_p: dict, in_p: dict) -> list[dict]:
    return [in_p if p["player_id"] == out_p["player_id"] else p for p in squad]


def _one_transfer(squad: list[dict], market: list[dict], *, bank: int, key: str):
    """Best single legal (out, in) by XI-`key` gain, or None."""
    cur = _best_xi_ids(squad, key)[1]
    have = {p["player_id"] for p in squad}
    best = None  # (gain, out, in, bank_after)
    for out_p in squad:
        for in_p in market:
            if in_p["player_id"] in have or in_p["position"] != out_p["position"]:
                continue
            bank_after = bank + out_p["now_cost"] - in_p["now_cost"]
            if bank_after < 0:
                continue
            after = _apply(squad, out_p, in_p)
            if any(v > 3 for v in _club_counts(after).values()):
                continue
            gain = _best_xi_ids(after, key)[1] - cur
            if best is None or gain > best[0]:
                best = (gain, out_p, in_p, bank_after)
    return best


def suggest_transfers(squad: list[dict[str, Any]], market: list[dict[str, Any]], *,
                      bank: int, free_transfers: int = 1, max_transfers: int = 2,
                      key: str = "xp", hit_cost: float = HIT_COST) -> list[dict]:
    """Greedy: at each step take the single transfer with the largest XI-`key`
    gain, respecting £bank, same-position swaps and max 3 per club. Returns one
    plan per k in 0..max_transfers, sorted by ``net`` desc; the k=0 plan is
    'roll your transfer'. Each plan: ``{transfers: [{out, in}], gain, hit, net}``.
    """
    plans = [{"transfers": [], "gain": 0.0, "hit": 0.0, "net": 0.0}]
    work = list(squad)
    cur_bank = bank
    total_gain = 0.0
    pool = list(market)
    for k in range(1, max_transfers + 1):
        step = _one_transfer(work, pool, bank=cur_bank, key=key)
        if step is None or step[0] <= 1e-9:
            break
        gain, out_p, in_p, cur_bank = step
        work = _apply(work, out_p, in_p)
        pool = [m for m in pool if m["player_id"] != in_p["player_id"]]
        total_gain += gain
        hit = hit_cost * max(0, k - free_transfers)
        plans.append({
            "transfers": plans[-1]["transfers"] + [{"out": out_p, "in": in_p}],
            "gain": round(total_gain, 2),
            "hit": round(hit, 2),
            "net": round(total_gain - hit, 2),
        })
    plans.sort(key=lambda p: p["net"], reverse=True)
    return plans


def chip_hints(calendar: list[dict], *, squad_team_ids: list[int],
               double_threshold: int = 3, blank_threshold: int = 4) -> list[dict]:
    """DGW/BGW chip hints from `gw_calendar`-style rows ({gameweek_id, doubles, blanks})."""
    ids = set(squad_team_ids)
    out: list[dict] = []
    for row in calendar:
        dbl = len(ids & set(row.get("doubles", [])))
        blk = len(ids & set(row.get("blanks", [])))
        if dbl >= double_threshold:
            out.append({"chip": "bench_boost", "gameweek_id": row["gameweek_id"],
                        "reason": f"{dbl} of your players have a double gameweek"})
            out.append({"chip": "triple_captain", "gameweek_id": row["gameweek_id"],
                        "reason": "a premium captain plays twice"})
        if blk >= blank_threshold:
            out.append({"chip": "free_hit", "gameweek_id": row["gameweek_id"],
                        "reason": f"{blk} of your players blank this gameweek"})
    return out
