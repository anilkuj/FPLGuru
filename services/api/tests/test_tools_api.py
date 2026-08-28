from datetime import UTC, datetime

from fplguru_core.models import (
    EntryPick,
    Fixture,
    Gameweek,
    LinkedTeam,
    Player,
    PlayerGwPrediction,
    Team,
)

_MV = "basic-v1"


async def _seed(db_session):
    db_session.add_all([Team(id=1, name="A", short_name="A"), Team(id=2, name="B", short_name="B")])
    db_session.add_all([
        Gameweek(id=5, name="GW5", deadline_time=datetime(2025, 9, 1, tzinfo=UTC), is_current=True),
        Gameweek(id=6, name="GW6", deadline_time=datetime(2025, 9, 8, tzinfo=UTC)),
    ])
    await db_session.commit()

    def mk(pid, pos, team, sel, tin=0, tout=0, dc=0):
        return pid, Player(id=pid, team_id=team, first_name="x", second_name="y",
                           web_name=f"P{pid}", position=pos, now_cost=50, status="a",
                           selected_by_percent=sel, transfers_in_event=tin,
                           transfers_out_event=tout, cost_change_event=dc)

    roster = [
        mk(1, "GK", 1, 20), mk(2, "DEF", 1, 55, tin=900, dc=1), mk(3, "DEF", 2, 40),
        mk(4, "DEF", 1, 35), mk(5, "MID", 2, 50, tout=800, dc=-1), mk(6, "MID", 1, 45),
        mk(7, "MID", 2, 30), mk(8, "MID", 1, 25), mk(9, "FWD", 2, 60), mk(10, "FWD", 1, 33),
        mk(11, "FWD", 2, 22),
    ]
    db_session.add_all([p for _, p in roster])
    db_session.add(LinkedTeam(id=1, fpl_entry_id=7, manager_name="Sam"))
    await db_session.commit()
    db_session.add_all([
        PlayerGwPrediction(player_id=pid, gameweek_id=5, horizon_gw=1, model_version=_MV,
                           xp=float(pid))
        for pid, _ in roster
    ])
    db_session.add_all([
        Fixture(id=50, gameweek_id=5, home_team_id=1, away_team_id=2, home_difficulty=3,
                away_difficulty=3),
        Fixture(id=51, gameweek_id=5, home_team_id=2, away_team_id=1, home_difficulty=3,
                away_difficulty=3),
        Fixture(id=60, gameweek_id=6, home_team_id=1, away_team_id=2, home_difficulty=3,
                away_difficulty=3),
    ])
    db_session.add_all([
        EntryPick(linked_team_id=1, gameweek_id=5, player_id=2, slot=1, multiplier=1),
        EntryPick(linked_team_id=1, gameweek_id=5, player_id=9, slot=2, multiplier=1),
    ])
    await db_session.commit()


async def test_trends(client, db_session):
    await _seed(db_session)
    body = (await client.get("/trends")).json()
    assert body["transfers_in"][0]["player_id"] == 2
    assert body["transfers_out"][0]["player_id"] == 5
    assert body["price_risers"][0]["player_id"] == 2
    assert body["price_fallers"][0]["player_id"] == 5


async def test_template(client, db_session):
    await _seed(db_session)
    body = (await client.get("/template")).json()
    assert len(body["xi"]) == 11
    assert body["formation"].count("-") == 2


async def test_template_diff(client, db_session):
    await _seed(db_session)
    body = (await client.get("/entries/7/template-diff")).json()
    assert "overlap" in body and isinstance(body["your_differentials"], list)


async def test_calendar_flags_double_in_gw5(client, db_session):
    await _seed(db_session)
    body = (await client.get("/calendar?from_gw=5&to_gw=6")).json()
    gw5 = next(c for c in body if c["gameweek_id"] == 5)
    assert sorted(gw5["doubles"]) == [1, 2]
    gw6 = next(c for c in body if c["gameweek_id"] == 6)
    assert gw6["doubles"] == []


async def test_overpowered(client, db_session):
    await _seed(db_session)
    body = (await client.get("/overpowered?horizon=1")).json()
    assert len(body["xi"]) == 11
    assert 9 in {p["player_id"] for p in body["xi"]}   # highest-xp forward
