"""Pure FPL analysis tools — no DB, no network."""
from __future__ import annotations

from typing import Any

__all__ = [
    "trends", "template_xi", "template_diff", "gw_calendar", "pick_overpowered_xi",
]

# valid outfield splits (DEF, MID, FWD); GK is always 1
_FORMATIONS = [(3, 4, 3), (3, 5, 2), (4, 4, 2), (4, 3, 3), (4, 5, 1), (5, 4, 1), (5, 3, 2)]
_POS_ORDER = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}


def _brief(p: dict[str, Any], value_key: str) -> dict:
    return {"player_id": p["player_id"], "web_name": p["web_name"],
            "position": p["position"], "value": p[value_key]}


def trends(players: list[dict[str, Any]], *, limit: int = 10) -> dict:
    def top(key: str, *, reverse: bool = True, keep=lambda p: True):
        ranked = sorted((p for p in players if keep(p)),
                        key=lambda p: (p.get(key, 0), p["player_id"]), reverse=reverse)
        return [_brief(p, key) for p in ranked[:limit]]

    return {
        "transfers_in": top("transfers_in_event"),
        "transfers_out": top("transfers_out_event"),
        "price_risers": top("cost_change_event", keep=lambda p: p.get("cost_change_event", 0) > 0),
        "price_fallers": [
            _brief(p, "cost_change_event")
            for p in sorted((x for x in players if x.get("cost_change_event", 0) < 0),
                            key=lambda p: (p["cost_change_event"], p["player_id"]))[:limit]
        ],
        "most_owned": top("selected_by_percent"),
    }


def _fill(players: list[dict], key: str) -> tuple[list[dict], float]:
    """Best XI + score for the formation that maximises the summed `key`."""
    by_pos: dict[str, list[dict]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}
    for p in players:
        if p["position"] in by_pos:
            by_pos[p["position"]].append(p)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda p: (p.get(key, 0), -p["player_id"]), reverse=True)

    best: tuple[list[dict], float] | None = None
    gk = by_pos["GK"][:1]
    for d, m, f in _FORMATIONS:
        if len(by_pos["DEF"]) < d or len(by_pos["MID"]) < m or len(by_pos["FWD"]) < f or not gk:
            continue
        xi = gk + by_pos["DEF"][:d] + by_pos["MID"][:m] + by_pos["FWD"][:f]
        score = sum(p.get(key, 0) for p in xi)
        if best is None or score > best[1]:
            best = (xi, score)
    if best is None:
        return [], 0.0
    return best[0], best[1]


def _formation_str(xi: list[dict]) -> str:
    n = {"DEF": 0, "MID": 0, "FWD": 0}
    for p in xi:
        if p["position"] in n:
            n[p["position"]] += 1
    return f"{n['DEF']}-{n['MID']}-{n['FWD']}"


def template_xi(players: list[dict[str, Any]]) -> dict:
    xi, own = _fill(players, "selected_by_percent")
    xi = sorted(xi, key=lambda p: (_POS_ORDER[p["position"]], -p.get("selected_by_percent", 0)))
    return {
        "formation": _formation_str(xi),
        "template_ownership": round(own, 1),
        "xi": [
            {"player_id": p["player_id"], "web_name": p["web_name"], "position": p["position"],
             "selected_by_percent": p.get("selected_by_percent", 0.0)}
            for p in xi
        ],
    }


def template_diff(picks: list[dict[str, Any]], template: dict) -> dict:
    tmpl_ids = {p["player_id"] for p in template.get("xi", [])}
    pick_ids = {p["player_id"] for p in picks}
    return {
        "overlap": len(tmpl_ids & pick_ids),
        "your_differentials": sorted(pick_ids - tmpl_ids),
        "template_only": sorted(tmpl_ids - pick_ids),
    }


def gw_calendar(fixtures: list[dict[str, Any]], gameweeks: list[dict[str, Any]], *,
                from_gw: int, to_gw: int, team_ids: list[int]) -> list[dict]:
    out = []
    for g in sorted(gameweeks, key=lambda g: g["id"]):
        gid = g["id"]
        if not (from_gw <= gid <= to_gw):
            continue
        counts = dict.fromkeys(team_ids, 0)
        for f in fixtures:
            if f.get("gameweek_id") != gid:
                continue
            for t in (f["home_team_id"], f["away_team_id"]):
                if t in counts:
                    counts[t] += 1
        out.append({
            "gameweek_id": gid,
            "counts": counts,
            "blanks": sorted(t for t, n in counts.items() if n == 0),
            "doubles": sorted(t for t, n in counts.items() if n >= 2),
        })
    return out


def pick_overpowered_xi(players: list[dict[str, Any]]) -> dict:
    xi, total = _fill(players, "xp")
    xi = sorted(xi, key=lambda p: (_POS_ORDER[p["position"]], -p.get("xp", 0)))
    return {
        "formation": _formation_str(xi),
        "total_xp": round(total, 2),
        "total_cost": sum(p.get("now_cost", 0) for p in xi),
        "xi": [
            {"player_id": p["player_id"], "web_name": p["web_name"], "position": p["position"],
             "xp": round(p.get("xp", 0.0), 2), "now_cost": p.get("now_cost", 0)}
            for p in xi
        ],
    }
