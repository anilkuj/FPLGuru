from fplguru_live import build_live_rows, project_bonus


def test_project_bonus_simple_321():
    # distinct BPS values 30 > 25 > 20 -> 3, 2, 1
    got = project_bonus({1: 30, 2: 25, 3: 20, 4: 10})
    assert got == {1: 3, 2: 2, 3: 1, 4: 0}


def test_project_bonus_tie_for_first_skips_two():
    # two tied on top -> both 3, next distinct -> 1 (no 2 awarded)
    got = project_bonus({1: 30, 2: 30, 3: 25, 4: 25})
    assert got == {1: 3, 2: 3, 3: 1, 4: 1}


def test_project_bonus_tie_for_second_skips_one():
    got = project_bonus({1: 40, 2: 30, 3: 30})
    assert got == {1: 3, 2: 2, 3: 2}


def test_project_bonus_non_positive_bps_gets_nothing():
    got = project_bonus({1: 0, 2: -3, 3: 12})
    assert got == {1: 0, 2: 0, 3: 3}


def test_project_bonus_empty():
    assert project_bonus({}) == {}


_PAYLOAD = {
    "elements": [
        # player 11: two fixtures (DGW) -> bonus summed across both
        {"id": 11, "stats": {"minutes": 90, "total_points": 8, "bps": 55},
         "explain": [
             {"fixture": 100, "stats": [{"identifier": "bps", "value": 30}]},
             {"fixture": 101, "stats": [{"identifier": "bps", "value": 25}]},
         ]},
        # player 12: one fixture, tops fixture 100
        {"id": 12, "stats": {"minutes": 90, "total_points": 6, "bps": 33},
         "explain": [{"fixture": 100, "stats": [{"identifier": "bps", "value": 33}]}]},
        # player 13: one fixture, below player 11 in fixture 101
        {"id": 13, "stats": {"minutes": 45, "total_points": 2, "bps": 10},
         "explain": [{"fixture": 101, "stats": [{"identifier": "bps", "value": 10}]}]},
        # player 14: did not feature -> no row
        {"id": 14, "stats": {"minutes": 0, "total_points": 0, "bps": 0}, "explain": []},
    ]
}


def test_build_live_rows_projects_and_sums_bonus():
    rows = {r["player_id"]: r for r in build_live_rows(3, _PAYLOAD)}
    assert set(rows) == {11, 12, 13}  # 14 excluded

    # fixture 100: bps 33 (p12) > 30 (p11) -> p12=3, p11=2
    # fixture 101: bps 25 (p11) > 10 (p13) -> p11=3, p13=2
    assert rows[11]["projected_bonus"] == 2 + 3
    assert rows[12]["projected_bonus"] == 3
    assert rows[13]["projected_bonus"] == 2

    assert rows[11]["gameweek_id"] == 3
    assert rows[11]["minutes"] == 90
    assert rows[11]["live_points"] == 8
    assert rows[11]["bps"] == 55
    assert rows[11]["total_points"] == 8 + 5  # live_points + projected_bonus


def test_build_live_rows_without_explain_uses_stats_bps_single_bucket():
    payload = {"elements": [
        {"id": 21, "stats": {"minutes": 90, "total_points": 5, "bps": 40}},
        {"id": 22, "stats": {"minutes": 90, "total_points": 3, "bps": 20}},
    ]}
    rows = {r["player_id"]: r for r in build_live_rows(3, payload)}
    # no explain -> all such players share one synthetic bucket, ranked by stats.bps
    assert rows[21]["projected_bonus"] == 3
    assert rows[22]["projected_bonus"] == 2
