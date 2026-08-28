from datetime import UTC, datetime

import fplguru_api.main as main_mod
from fplguru_core.models import (
    EntryPick,
    Gameweek,
    LinkedTeam,
    Player,
    PlayerGwPrediction,
    Team,
)

_MV = "basic-v1"


async def _seed(db_session):
    db_session.add_all([
        Team(id=1, name="A", short_name="LIV"),
        Team(id=2, name="B", short_name="MCI"),
    ])
    db_session.add(Gameweek(id=5, name="GW5", deadline_time=datetime(2025, 9, 1, tzinfo=UTC),
                            is_current=True))
    await db_session.commit()
    db_session.add_all([
        Player(id=1, team_id=1, first_name="M", second_name="S", web_name="Salah",
               position="MID", now_cost=130, status="a"),
        Player(id=2, team_id=1, first_name="A", second_name="I", web_name="Isak",
               position="FWD", now_cost=100, status="a"),
        Player(id=3, team_id=2, first_name="B", second_name="B", web_name="Bench",
               position="DEF", now_cost=45, status="a"),
        Player(id=9, team_id=2, first_name="E", second_name="H", web_name="Haaland",
               position="FWD", now_cost=150, status="a"),
    ])
    db_session.add(LinkedTeam(id=1, fpl_entry_id=7, manager_name="Sam"))
    await db_session.commit()
    db_session.add_all([
        PlayerGwPrediction(player_id=1, gameweek_id=5, horizon_gw=1, model_version=_MV, xp=7.1),
        PlayerGwPrediction(player_id=2, gameweek_id=5, horizon_gw=1, model_version=_MV, xp=6.4),
        PlayerGwPrediction(player_id=3, gameweek_id=5, horizon_gw=1, model_version=_MV, xp=5.0),
        PlayerGwPrediction(player_id=9, gameweek_id=5, horizon_gw=1, model_version=_MV, xp=8.8),
    ])
    db_session.add_all([
        EntryPick(linked_team_id=1, gameweek_id=5, player_id=1, slot=1, multiplier=2,
                  is_captain=True, is_vice=False),
        EntryPick(linked_team_id=1, gameweek_id=5, player_id=2, slot=2, multiplier=1),
        EntryPick(linked_team_id=1, gameweek_id=5, player_id=3, slot=12, multiplier=0),
    ])
    await db_session.commit()


async def test_captain_ranks_and_uses_templated_rationale_when_llm_off(client, db_session):
    await _seed(db_session)                       # gemini_api_key defaults to "" -> no LLM
    body = (await client.get("/entries/7/captain?horizon=1")).json()
    assert [p["player_id"] for p in body["constrained"]] == [1, 2]      # bench (3) excluded
    assert body["unconstrained"][0]["player_id"] == 9                   # Haaland global best
    assert "Salah" in body["rationale"]["constrained"]
    assert body["rationale_source"] == "template"


async def test_captain_uses_llm_and_caches(client, db_session, monkeypatch):
    await _seed(db_session)

    calls = {"n": 0}

    async def _fake(db, feature, prompt, *, max_output_tokens=200):
        calls["n"] += 1
        return "Captain Salah: home fixture, in form."

    monkeypatch.setattr(main_mod, "generate_within_budget", _fake)

    b1 = (await client.get("/entries/7/captain?horizon=1")).json()
    assert b1["rationale"]["constrained"] == "Captain Salah: home fixture, in form."
    assert b1["rationale_source"] == "llm"

    b2 = (await client.get("/entries/7/captain?horizon=1")).json()
    assert b2["rationale"]["constrained"] == "Captain Salah: home fixture, in form."
    assert calls["n"] == 2   # 2 picks on the first request; second request is all cache


async def test_captain_unknown_entry_404(client, db_session):
    assert (await client.get("/entries/999/captain")).status_code == 404
