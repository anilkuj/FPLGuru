from fplguru_alerts import availability_alerts, dgw_bgw_alerts, score_alert


def test_score_captain_hard_out_pre_deadline_clamps_to_100():
    a = {"type": "availability", "payload": {"status": "i"}}
    assert score_alert(a, in_xi=True, is_captain=True, before_deadline=True) == 100


def test_score_bench_doubtful():
    a = {"type": "availability", "payload": {"status": "d"}}
    assert score_alert(a, in_xi=False, is_captain=False, before_deadline=True) == 70


def test_score_dgw_xi_pre_deadline():
    a = {"type": "dgw", "payload": {}}
    assert score_alert(a, in_xi=True, is_captain=False, before_deadline=True) == 65


def test_score_bgw_bench_post_deadline():
    a = {"type": "bgw", "payload": {}}
    assert score_alert(a, in_xi=False, is_captain=False, before_deadline=False) == 45


_PICKS = [
    {"player_id": 1, "web_name": "Salah", "status": "a", "chance_of_playing_next_round": None,
     "news": "", "multiplier": 2, "is_captain": True, "is_vice": False, "team_id": 10},
    {"player_id": 2, "web_name": "Isak", "status": "i", "chance_of_playing_next_round": 0,
     "news": "Knee injury - expected back 20 Oct", "multiplier": 1, "is_captain": False,
     "is_vice": False, "team_id": 11},
    {"player_id": 3, "web_name": "Gordon", "status": "a", "chance_of_playing_next_round": 75,
     "news": "Knock", "multiplier": 0, "is_captain": False, "is_vice": False, "team_id": 11},
]


def test_availability_alerts_only_flags_non_available():
    out = availability_alerts(_PICKS, gameweek_id=9)
    keys = {a["dedup_key"]: a for a in out}
    assert set(keys) == {"avail:2:i:0", "avail:3:a:75"}          # player 1 is fine -> no alert
    isak = keys["avail:2:i:0"]
    assert isak["type"] == "availability"
    assert isak["player_id"] == 2
    assert isak["gameweek_id"] == 9
    assert "Knee injury" in isak["body"]
    assert isak["payload"]["status"] == "i" and isak["payload"]["in_xi"] is True
    assert keys["avail:3:a:75"]["payload"]["in_xi"] is False


def test_dgw_bgw_alerts_from_owned_teams_and_fixture_counts():
    owned_team_ids = {10, 11}
    fixture_counts = {10: 2, 11: 0, 12: 2}   # 12 not owned -> ignored
    names_by_team = {10: ["Salah"], 11: ["Isak", "Gordon"]}
    out = {a["dedup_key"]: a for a in dgw_bgw_alerts(
        owned_team_ids, fixture_counts, names_by_team, gameweek_id=9)}
    assert set(out) == {"dgw:10:9", "bgw:11:9"}
    assert out["dgw:10:9"]["type"] == "dgw"
    assert out["bgw:11:9"]["type"] == "bgw"
    assert "Isak" in out["bgw:11:9"]["body"] and "Gordon" in out["bgw:11:9"]["body"]
    assert out["bgw:11:9"]["payload"]["player_names"] == ["Isak", "Gordon"]
