from fplguru_h2h import compare_squads


def _p(pid, pos, xp, club=1):
    return {"player_id": pid, "web_name": f"P{pid}", "position": pos,
            "now_cost": 50, "team_id": club, "xp": xp}


def _full(base, xp_map):
    s, pid = [], base
    for pos, n in (("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)):
        for _ in range(n):
            s.append(_p(pid, pos, xp_map.get(pid, 10.0)))
            pid += 1
    return s


def test_compare_reports_margin_diffs_and_captains():
    mine = _full(1, {3: 30.0})  # my DEF id 3 is elite -> tops my XI
    theirs = _full(1, {})
    theirs[7] = _p(99, "DEF", 25.0)  # they swap in id 99 (I keep my id 8)
    theirs[8] = _p(98, "MID", 5.0)   # they swap in id 98 (I keep my id 9)
    r = compare_squads(mine, theirs, horizon=3)
    assert r["your_xi_total"] > 0 and r["their_xi_total"] > 0
    assert round(r["margin"], 2) == round(r["your_xi_total"] - r["their_xi_total"], 2)
    assert {p["player_id"] for p in r["their_differentials"]} == {99, 98}
    assert {p["player_id"] for p in r["your_differentials"]} == {8, 9}
    assert r["your_captain"]["player_id"] == 3  # elite DEF tops my XI
    assert r["shared_count"] == 13
    assert r["strategy"]
    # their_differentials sorted by xp desc
    xps = [p["xp"] for p in r["their_differentials"]]
    assert xps == sorted(xps, reverse=True)


def test_strategy_text_switches_on_who_leads():
    even = _full(1, {})
    ahead = compare_squads(_full(1, {3: 60.0}), even, horizon=1)
    behind = compare_squads(even, _full(1, {3: 60.0}), horizon=1)
    assert "ahead" in ahead["strategy"].lower()
    assert "behind" in behind["strategy"].lower()


def test_identical_squads_are_level_with_full_overlap():
    s = _full(1, {})
    r = compare_squads(s, [dict(p) for p in s], horizon=2)
    assert r["margin"] == 0.0
    assert r["your_differentials"] == [] and r["their_differentials"] == []
    assert r["same_captain"] is True
    assert "level" in r["strategy"].lower()
