from fplguru_fdr import compute_fdr


def _team(tid, sn, sh, sa):
    return {"id": tid, "short_name": sn, "strength_overall_home": sh, "strength_overall_away": sa}


def _fx(fid, gw, h, a, hs=None, as_=None, finished=False):
    return {"id": fid, "gameweek_id": gw, "home_team_id": h, "away_team_id": a,
            "home_score": hs, "away_score": as_, "finished": finished}


TEAMS = [_team(1, "AAA", 5, 5), _team(2, "BBB", 3, 3), _team(3, "CCC", 4, 4)]
GWS = [{"id": g, "is_next": g == 4, "finished": g < 4} for g in range(1, 9)]


def test_preseason_is_strength_only():
    fx = [_fx(40, 4, 2, 1), _fx(41, 5, 1, 2)]
    out = {t["short_name"]: t for t in compute_fdr(TEAMS, fx, GWS, start_gw=4, horizon=2)}
    bbb = out["BBB"]
    f0 = next(f for f in bbb["fixtures"] if f["gameweek_id"] == 4)
    assert f0["is_home"] is True and f0["opponent_short"] == "AAA"
    assert abs(f0["fdr"] - 5.0) < 1e-6 and f0["band"] == 5
    aaa = out["AAA"]
    f1 = next(f for f in aaa["fixtures"] if f["gameweek_id"] == 5)
    assert abs(f1["fdr"] - (1.0 + 4.0 * (1 / 3))) < 1e-6


def test_form_pulls_fdr_toward_recent_results():
    finished = [
        _fx(1, 1, 3, 1, hs=0, as_=4, finished=True),
        _fx(2, 2, 2, 3, hs=3, as_=0, finished=True),
        _fx(3, 3, 3, 1, hs=1, as_=3, finished=True),
    ]
    fut = [_fx(40, 4, 2, 3)]
    out = {
        t["short_name"]: t
        for t in compute_fdr(TEAMS, finished + fut, GWS, start_gw=4, horizon=1)
    }
    f = out["BBB"]["fixtures"][0]
    assert f["att_fdr"] < f["def_fdr"]
    assert 1.0 <= f["fdr"] <= 5.0


def test_avg_fdr_present_and_sorted_input_ok():
    fx = [_fx(40, 4, 1, 2), _fx(41, 5, 2, 1), _fx(42, 4, 3, 1)]
    out = compute_fdr(TEAMS, fx, GWS, start_gw=4, horizon=3)
    for t in out:
        assert "avg_fdr" in t and (t["avg_fdr"] is None or 1.0 <= t["avg_fdr"] <= 5.0)
    assert {t["short_name"] for t in out} == {"AAA", "BBB", "CCC"}
