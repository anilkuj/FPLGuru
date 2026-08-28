from fplguru_optimize import best_xi


def _p(pid, pos, xp, cost=50, club=1):
    return {"player_id": pid, "position": pos, "web_name": f"P{pid}",
            "xp": xp, "now_cost": cost, "team_id": club}


def _squad():
    s, pid = [], 1
    for pos, n in (("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)):
        for _ in range(n):
            s.append(_p(pid, pos, xp=30 - pid, club=1 + pid % 4))
            pid += 1
    return s


def test_best_xi_picks_top_scoring_legal_eleven():
    r = best_xi(_squad(), key="xp")
    assert len(r["xi"]) == 11 and len(r["bench"]) == 4
    assert sum(1 for p in r["xi"] if p["position"] == "GK") == 1
    xi_by_xp = sorted(r["xi"], key=lambda p: -p["xp"])
    assert r["captain"]["player_id"] == xi_by_xp[0]["player_id"]
    assert r["vice"]["player_id"] == xi_by_xp[1]["player_id"]
    assert r["total"] == round(sum(p["xp"] for p in r["xi"]), 2)
    assert r["formation"].count("-") == 2


def test_best_xi_bench_keeps_a_gk_and_lists_it_first():
    r = best_xi(_squad(), key="xp")
    assert sum(1 for p in r["bench"] if p["position"] == "GK") == 1
    assert r["bench"][0]["position"] == "GK"
    assert len([p for p in r["bench"] if p["position"] != "GK"]) == 3


def test_best_xi_total_is_max_over_formations():
    r = best_xi(_squad(), key="xp")
    # (5,4,1) is optimal for this squad: GK29 + DEF(27+26+25+24+23) + MID(22+21+20+19) + FWD17
    assert r["formation"] == "5-4-1"
    assert r["total"] == 29 + 125 + 82 + 17


def test_best_xi_empty_squad_is_safe():
    r = best_xi([], key="xp")
    assert r["xi"] == [] and r["captain"] is None
