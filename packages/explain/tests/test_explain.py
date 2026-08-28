from fplguru_explain import DRIVER_PHRASES, explanation_prompt, template_explanation

PLAYER = {"web_name": "Saka", "position": "MID", "team_short": "ARS"}
FIX = [
    {"opponent_short": "LUT", "was_home": True, "difficulty": 2},
    {"opponent_short": "CHE", "was_home": False, "difficulty": 4},
]
DRIVERS = [("form_xg_5", 0.9), ("opp_conceded_to_pos_5", 0.4), ("starts_rate_5", -0.3)]


def test_template_is_deterministic_and_mentions_player_and_xp():
    t = template_explanation(PLAYER, xp=6.4, floor=3.1, ceiling=9.0, drivers=DRIVERS, horizon=2)
    assert "Saka" in t and "6.4" in t
    assert DRIVER_PHRASES["form_xg_5"] in t
    assert t == template_explanation(PLAYER, xp=6.4, floor=3.1, ceiling=9.0,
                                     drivers=DRIVERS, horizon=2)


def test_template_handles_no_drivers():
    t = template_explanation(PLAYER, xp=2.0, floor=0.0, ceiling=4.0, drivers=[], horizon=1)
    assert "no single dominant factor" in t


def test_prompt_lists_drivers_with_direction_and_forbids_preamble():
    p = explanation_prompt(PLAYER, FIX, DRIVERS, xp=6.4, floor=3.1, ceiling=9.0, horizon=2)
    assert "Saka" in p and "6.4" in p
    assert "raises" in p.lower() and "lowers" in p.lower()
    assert "no preamble" in p.lower()
    assert "LUT (H, FDR 2)" in p


def test_prompt_survives_empty_fixtures_and_drivers():
    p = explanation_prompt(PLAYER, [], [], xp=1.0, floor=0.0, ceiling=2.0, horizon=3)
    assert "unknown" in p and "none" in p
