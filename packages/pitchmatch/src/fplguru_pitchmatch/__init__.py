"""Pure PitchAPI <-> FPL identity matching + match xG normalization."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

__all__ = ["match_teams", "match_players", "normalize_match_xg"]

# PitchAPI full name -> FPL short name fragments that don't normalize cleanly
_TEAM_ALIASES = {
    "manchester city": "man city",
    "manchester united": "man utd",
    "manchester utd": "man utd",
    "newcastle united": "newcastle",
    "tottenham hotspur": "spurs",
    "tottenham": "spurs",
    "wolverhampton wanderers": "wolves",
    "nottingham forest": "nott m forest",
    "brighton hove albion": "brighton",
    "brighton and hove albion": "brighton",
    "west ham united": "west ham",
    "sheffield united": "sheffield utd",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).strip()


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def match_teams(fpl_teams: list[dict[str, Any]],
                pitch_teams: list[dict[str, Any]]) -> dict[str, int]:
    by_norm: dict[str, int] = {}
    for t in fpl_teams:
        by_norm[_squash(_norm(t["name"]))] = t["id"]
        by_norm[_squash(_norm(t["short_name"]))] = t["id"]
    out: dict[str, int] = {}
    for pt in pitch_teams:
        n = _squash(_norm(pt["name"]))
        n = _TEAM_ALIASES.get(n, n)
        if n in by_norm:
            out[pt["id"]] = by_norm[n]
            continue
        hit = next((fid for key, fid in by_norm.items()
                    if key and (key in n or n in key)), None)
        if hit is not None:
            out[pt["id"]] = hit
    return out


def _pitch_last_first(name: str) -> tuple[str, str]:
    parts = _norm(name).split()
    if not parts:
        return "", ""
    last = parts[-1]
    first_initial = parts[0][0] if parts[0] else ""
    return last, first_initial


def match_players(fpl_players: list[dict[str, Any]], pitch_players: list[dict[str, Any]],
                  team_map: dict[str, int]) -> tuple[dict[str, int], list[dict]]:
    idx: dict[tuple[int, str], list[dict]] = {}
    for p in fpl_players:
        base = p["second_name"] if p.get("second_name") else p["web_name"]
        surname = _norm(base).split()[-1] if _norm(base) else ""
        idx.setdefault((p["team_id"], surname), []).append(p)

    matched: dict[str, int] = {}
    unmatched: list[dict] = []
    for pp in pitch_players:
        pid = pp["player"]["id"]
        fpl_team = team_map.get(pp.get("team_id"))
        last, initial = _pitch_last_first(pp["player"].get("name", ""))
        cands = idx.get((fpl_team, last), []) if fpl_team is not None else []
        if len(cands) == 1:
            matched[pid] = cands[0]["id"]
        elif len(cands) > 1 and initial:
            narrowed = [c for c in cands if _norm(c["first_name"])[:1] == initial]
            if len(narrowed) == 1:
                matched[pid] = narrowed[0]["id"]
            else:
                unmatched.append(pp)
        else:
            unmatched.append(pp)
    return matched, unmatched


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def normalize_match_xg(shots: list[dict[str, Any]],
                       advanced: list[dict[str, Any]]) -> list[dict]:
    def _blank(pid: str) -> dict:
        return {"pitch_player_id": pid, "xg": 0.0, "xg_ot": 0.0, "xag": 0.0,
                "minutes": 0, "key_passes": 0, "chances_created": 0, "vaep": 0.0}

    agg: dict[str, dict] = {}
    for s in shots:
        pid = (s.get("player") or {}).get("id")
        if not pid:
            continue
        r = agg.setdefault(pid, _blank(pid))
        r["xg"] += _f(s.get("expected_goals"))
        r["xg_ot"] += _f(s.get("expected_goals_on_target"))
    for a in advanced:
        pid = (a.get("player") or {}).get("id")
        if not pid:
            continue
        r = agg.setdefault(pid, _blank(pid))
        r["minutes"] = int(_f(a.get("minutes_played")))
        r["xag"] = _f((a.get("creation") or {}).get("xag"))
        r["chances_created"] = int(_f((a.get("creation") or {}).get("chances_created")))
        r["key_passes"] = int(_f((a.get("passing") or {}).get("key_passes")))
        r["vaep"] = _f((a.get("possession_value") or {}).get("vaep_total"))
    return list(agg.values())
