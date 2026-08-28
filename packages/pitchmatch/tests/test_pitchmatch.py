from fplguru_pitchmatch import match_players, match_teams, normalize_match_xg


def test_match_teams_by_normalized_name_and_alias():
    fpl = [{"id": 11, "name": "Man City", "short_name": "MCI"},
           {"id": 12, "name": "Nott'm Forest", "short_name": "NFO"}]
    pitch = [{"id": "t_a", "name": "Manchester City"},
             {"id": "t_b", "name": "Nottingham Forest"},
             {"id": "t_c", "name": "Unknown FC"}]
    got = match_teams(fpl, pitch)
    assert got == {"t_a": 11, "t_b": 12}          # t_c unmatched -> omitted


def test_match_players_uses_surname_initial_and_team():
    fpl = [
        {"id": 1, "web_name": "Haaland", "first_name": "Erling", "second_name": "Haaland",
         "team_id": 11},
        {"id": 2, "web_name": "B.Silva", "first_name": "Bernardo", "second_name": "Silva",
         "team_id": 11},
        {"id": 3, "web_name": "Silva", "first_name": "Thiago", "second_name": "Silva",
         "team_id": 12},
    ]
    pitch = [
        {"player": {"id": "p_h", "name": "E. Haaland"}, "team_id": "t_a"},
        {"player": {"id": "p_s", "name": "B. Silva"}, "team_id": "t_a"},
        {"player": {"id": "p_x", "name": "Zz Nobody"}, "team_id": "t_a"},
    ]
    team_map = {"t_a": 11}
    matched, unmatched = match_players(fpl, pitch, team_map)
    assert matched == {"p_h": 1, "p_s": 2}        # surname + initial + team
    assert [u["player"]["id"] for u in unmatched] == ["p_x"]


def test_normalize_match_xg_merges_shots_and_advanced():
    shots = [
        {"player": {"id": "p_h"}, "expected_goals": 0.3, "expected_goals_on_target": 0.2},
        {"player": {"id": "p_h"}, "expected_goals": 0.15},
        {"player": {"id": "p_s"}, "expected_goals": 0.05},
    ]
    adv = [
        {"player": {"id": "p_h"}, "minutes_played": 90,
         "possession_value": {"vaep_total": 0.8},
         "passing": {"key_passes": 1}, "creation": {"xag": 0.22, "chances_created": 2}},
        {"player": {"id": "p_s"}, "minutes_played": 78,
         "creation": {"xag": 0.4}},
    ]
    rows = {r["pitch_player_id"]: r for r in normalize_match_xg(shots, adv)}
    assert round(rows["p_h"]["xg"], 2) == 0.45
    assert round(rows["p_h"]["xg_ot"], 2) == 0.20
    assert rows["p_h"]["xag"] == 0.22
    assert rows["p_h"]["minutes"] == 90
    assert rows["p_h"]["key_passes"] == 1
    assert rows["p_h"]["vaep"] == 0.8
    assert rows["p_s"]["xg"] == 0.05 and rows["p_s"]["xag"] == 0.4 and rows["p_s"]["minutes"] == 78
