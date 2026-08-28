from fplguru_optimize import chip_hints, suggest_transfers


def _p(pid, pos, xp, cost=50, club=1):
    return {"player_id": pid, "position": pos, "web_name": f"P{pid}",
            "xp": xp, "now_cost": cost, "team_id": club}


def _squad():
    s, pid = [], 1
    for pos, n in (("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)):
        for _ in range(n):
            s.append(_p(pid, pos, xp=20.0, cost=50, club=1 + pid % 5))
            pid += 1
    return s


def test_suggest_transfers_finds_a_clear_upgrade():
    squad = _squad()
    squad[7]["xp"] = 5.0  # pid 8 is a MID, make it weak so it starts on the bench / drags XI
    market = [_p(99, "MID", xp=40.0, cost=50, club=9)]
    plans = suggest_transfers(squad, market, bank=0, free_transfers=1,
                              max_transfers=1, key="xp")
    best = plans[0]
    assert best["transfers"][0]["out"]["player_id"] == 8
    assert best["transfers"][0]["in"]["player_id"] == 99
    assert best["gain"] > 0 and best["hit"] == 0.0 and best["net"] == best["gain"]


def test_second_transfer_charges_a_hit():
    squad = _squad()
    squad[7]["xp"] = 5.0
    squad[8]["xp"] = 5.0
    market = [_p(98, "MID", 40.0, 50, 9), _p(99, "MID", 41.0, 50, 10)]
    plans = suggest_transfers(squad, market, bank=0, free_transfers=1,
                              max_transfers=2, key="xp")
    two = next(p for p in plans if len(p["transfers"]) == 2)
    assert two["hit"] == 4.0
    assert two["net"] == round(two["gain"] - 4.0, 2)


def test_transfer_respects_budget_and_club_cap():
    squad = _squad()
    market = [_p(99, "MID", 99.0, cost=130, club=1)]  # unaffordable and club 1 already full-ish
    plans = suggest_transfers(squad, market, bank=0, free_transfers=1,
                              max_transfers=1, key="xp")
    assert plans[0]["transfers"] == []  # nothing legal -> the roll plan wins


def test_chip_hints_flags_double_and_blank():
    cal = [
        {"gameweek_id": 30, "doubles": [1, 2, 3], "blanks": []},
        {"gameweek_id": 33, "doubles": [], "blanks": [1, 2, 3, 4, 5, 6]},
    ]
    hints = chip_hints(cal, squad_team_ids=[1, 2, 3, 4, 5])
    kinds = {(h["chip"], h["gameweek_id"]) for h in hints}
    assert ("bench_boost", 30) in kinds
    assert ("triple_captain", 30) in kinds
    assert ("free_hit", 33) in kinds
