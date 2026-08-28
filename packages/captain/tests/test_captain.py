from fplguru_captain import rank_captains, rationale_prompt


def _sq(pid, name, pos, xp, xi=True):
    return {"player_id": pid, "web_name": name, "position": pos, "xp": xp,
            "in_xi": xi, "team_short": "LIV"}


def test_rank_captains_constrained_is_from_xi_only():
    squad = [_sq(1, "Salah", "MID", 7.1), _sq(2, "Isak", "FWD", 6.4),
             _sq(3, "Bench", "DEF", 9.9, xi=False)]
    allp = squad + [_sq(9, "Haaland", "FWD", 8.8), _sq(10, "Palmer", "MID", 7.5)]
    out = rank_captains(squad, allp, top=2)
    # constrained: only XI players -> bench (id 3, xp 9.9) is excluded
    assert [p["player_id"] for p in out["constrained"]] == [1, 2]
    assert out["constrained"][0]["xp"] == 7.1
    # unconstrained: any player, incl. your own bench -> highest xp first
    assert [p["player_id"] for p in out["unconstrained"]] == [3, 9]


def test_rank_captains_dedup_and_stable_tiebreak():
    squad = [_sq(5, "A", "MID", 5.0), _sq(6, "B", "MID", 5.0)]
    out = rank_captains(squad, squad, top=5)
    assert [p["player_id"] for p in out["constrained"]] == [5, 6]   # equal xp -> by id


def test_rationale_prompt_mentions_pick_and_alternatives():
    pick = _sq(1, "Salah", "MID", 7.1)
    alts = [_sq(2, "Isak", "FWD", 6.4)]
    p = rationale_prompt(pick, alts, kind="constrained", horizon=3)
    assert "Salah" in p and "Isak" in p and "3" in p
    assert "one" in p.lower() or "two" in p.lower() or "sentence" in p.lower()
