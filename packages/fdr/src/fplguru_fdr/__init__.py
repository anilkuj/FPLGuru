"""Platform FDR: opponent strength tier blended with recent goals-for/against form.

Pure — takes plain dicts, returns plain dicts. No DB, no network.
"""
from __future__ import annotations

_FORM_W = 0.45
_DEFAULT_BASELINE = 1.4

__all__ = ["compute_fdr"]


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _strength_fdr(s: int | None) -> float:
    if s is None:
        return 3.0
    return 1.0 + 4.0 * _clamp((s - 2) / 3.0, 0.0, 1.0)


def compute_fdr(teams, fixtures, gameweeks, *, start_gw: int, horizon: int,
                form_window: int = 5) -> list[dict]:
    by_id = {t["id"]: t for t in teams}
    short = {t["id"]: t["short_name"] for t in teams}
    target_gws = {
        g["id"] for g in gameweeks if start_gw <= g["id"] < start_gw + horizon
    }

    played: dict[int, list[tuple[int, int]]] = {}
    ordered = sorted(
        (f for f in fixtures if f["finished"] and f["home_score"] is not None
         and f["away_score"] is not None),
        key=lambda f: (f["gameweek_id"] or 0, f["id"]),
    )
    for f in ordered:
        h, a = f["home_team_id"], f["away_team_id"]
        hs, as_ = f["home_score"], f["away_score"]
        played.setdefault(h, []).append((hs, as_))
        played.setdefault(a, []).append((as_, hs))

    def form(team_id: int) -> tuple[float, float] | None:
        rows = played.get(team_id, [])[-form_window:]
        if not rows:
            return None
        gf = sum(r[0] for r in rows) / len(rows)
        ga = sum(r[1] for r in rows) / len(rows)
        return gf, ga

    _goals = [
        v for tid in played for pair in [form(tid)] if pair is not None for v in pair
    ]
    baseline = (sum(_goals) / len(_goals)) if _goals else _DEFAULT_BASELINE

    out: list[dict] = []
    for t in teams:
        tid = t["id"]
        rows = []
        for f in fixtures:
            if f["gameweek_id"] not in target_gws:
                continue
            if tid == f["home_team_id"]:
                is_home, opp = True, f["away_team_id"]
            elif tid == f["away_team_id"]:
                is_home, opp = False, f["home_team_id"]
            else:
                continue
            opp_t = by_id.get(opp, {})
            opp_venue_strength = (
                opp_t.get("strength_overall_away") if is_home
                else opp_t.get("strength_overall_home")
            )
            s_fdr = _strength_fdr(opp_venue_strength)

            opp_form = form(opp)
            if opp_form is None:
                att_fdr = def_fdr = s_fdr
                opp_form_out = None
            else:
                gf, ga = opp_form
                att_form = 1.0 + 4.0 * _clamp(1.0 - ga / (2.0 * baseline), 0.0, 1.0)
                def_form = 1.0 + 4.0 * _clamp(gf / (2.0 * baseline), 0.0, 1.0)
                att_fdr = (1 - _FORM_W) * s_fdr + _FORM_W * att_form
                def_fdr = (1 - _FORM_W) * s_fdr + _FORM_W * def_form
                opp_form_out = {"gf_pg": round(gf, 2), "ga_pg": round(ga, 2)}

            fdr = (att_fdr + def_fdr) / 2.0
            rows.append({
                "gameweek_id": f["gameweek_id"],
                "opponent_id": opp,
                "opponent_short": short.get(opp, "?"),
                "is_home": is_home,
                "att_fdr": round(att_fdr, 2),
                "def_fdr": round(def_fdr, 2),
                "fdr": fdr,
                "band": int(round(fdr)),
                "opponent_form": opp_form_out,
            })
        rows.sort(key=lambda r: (r["gameweek_id"], r["opponent_id"]))
        avg = round(sum(r["fdr"] for r in rows) / len(rows), 2) if rows else None
        out.append({
            "team_id": tid, "short_name": t["short_name"],
            "avg_fdr": avg, "fixtures": rows,
        })
    out.sort(key=lambda t: (t["avg_fdr"] is None, t["avg_fdr"] or 0.0))
    return out
