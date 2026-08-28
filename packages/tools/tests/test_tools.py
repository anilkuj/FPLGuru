from fplguru_tools import (
    gw_calendar,
    pick_overpowered_xi,
    template_diff,
    template_xi,
    trends,
)


def _p(pid, pos, sel, tin=0, tout=0, dc=0, team=1, name=None):
    return {"player_id": pid, "web_name": name or f"P{pid}", "position": pos, "team_id": team,
            "selected_by_percent": sel, "transfers_in_event": tin, "transfers_out_event": tout,
            "cost_change_event": dc, "now_cost": 50}


def test_trends_ranks_each_bucket():
    ps = [
        _p(1, "MID", 40, tin=900, tout=10, dc=1),
        _p(2, "FWD", 30, tin=50, tout=800, dc=-1),
        _p(3, "DEF", 55, tin=100, tout=100, dc=0),
    ]
    out = trends(ps, limit=2)
    assert [x["player_id"] for x in out["transfers_in"]] == [1, 3]
    assert [x["player_id"] for x in out["transfers_out"]] == [2, 3]
    assert [x["player_id"] for x in out["price_risers"]] == [1]
    assert [x["player_id"] for x in out["price_fallers"]] == [2]
    assert [x["player_id"] for x in out["most_owned"]] == [3, 1]


def test_template_xi_picks_most_owned_valid_formation():
    ps = (
        [_p(100, "GK", 60)]
        + [_p(200 + i, "DEF", 50 - i) for i in range(6)]
        + [_p(300 + i, "MID", 40 - i) for i in range(6)]
        + [_p(400 + i, "FWD", 30 - i) for i in range(4)]
    )
    xi = template_xi(ps)
    assert xi["formation"] in {"3-4-3", "3-5-2", "4-4-2", "4-3-3", "4-5-1", "5-4-1", "5-3-2"}
    assert len([p for p in xi["xi"] if p["position"] == "GK"]) == 1
    assert len(xi["xi"]) == 11
    assert xi["xi"][0]["player_id"] == 100          # the GK
    picked_def = {p["player_id"] for p in xi["xi"] if p["position"] == "DEF"}
    assert 200 in picked_def


def test_template_diff_counts_overlap_and_differentials():
    tmpl = {"xi": [{"player_id": 1}, {"player_id": 2}, {"player_id": 3}]}
    picks = [{"player_id": 2}, {"player_id": 3}, {"player_id": 9}]
    d = template_diff(picks, tmpl)
    assert d["overlap"] == 2
    assert d["your_differentials"] == [9]
    assert d["template_only"] == [1]


def test_gw_calendar_flags_blanks_and_doubles():
    fixtures = [
        {"gameweek_id": 5, "home_team_id": 1, "away_team_id": 2},
        {"gameweek_id": 5, "home_team_id": 3, "away_team_id": 1},   # team 1 plays twice
        {"gameweek_id": 6, "home_team_id": 2, "away_team_id": 3},   # team 1 blank
    ]
    gws = [{"id": 5}, {"id": 6}]
    cal = {c["gameweek_id"]: c
           for c in gw_calendar(fixtures, gws, from_gw=5, to_gw=6, team_ids=[1, 2, 3])}
    assert cal[5]["doubles"] == [1]
    assert cal[5]["blanks"] == []
    assert cal[6]["blanks"] == [1]
    assert cal[6]["doubles"] == []


def test_pick_overpowered_xi_maximises_xp_within_a_valid_formation():
    ps = (
        [{"player_id": 1, "web_name": "GK", "position": "GK", "team_id": 1, "now_cost": 45,
          "xp": 5}]
        + [{"player_id": 10 + i, "web_name": f"D{i}", "position": "DEF", "team_id": 2,
            "now_cost": 45, "xp": 6 - i} for i in range(5)]
        + [{"player_id": 20 + i, "web_name": f"M{i}", "position": "MID", "team_id": 3,
            "now_cost": 60, "xp": 8 - i} for i in range(5)]
        + [{"player_id": 30 + i, "web_name": f"F{i}", "position": "FWD", "team_id": 4,
            "now_cost": 70, "xp": 9 - i} for i in range(3)]
    )
    xi = pick_overpowered_xi(ps)
    assert len(xi["xi"]) == 11
    assert xi["formation"].count("-") == 2
    assert 30 in {p["player_id"] for p in xi["xi"]}
    assert xi["total_xp"] == round(sum(p["xp"] for p in xi["xi"]), 2)
