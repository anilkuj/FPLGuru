from datetime import UTC, datetime

from fplguru_core.models import (
    EntryGwHistory,
    EntryPick,
    Fixture,
    Gameweek,
    LinkedTeam,
    Player,
    PlayerGwPrediction,
    Team,
)

_SHAPE = [("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)]


async def _seed(db_session):
    db_session.add_all([Team(id=t, name=f"T{t}", short_name=f"T{t}") for t in range(1, 8)])
    db_session.add_all([
        Gameweek(id=g, name=f"GW{g}", deadline_time=datetime(2025, 8, g, tzinfo=UTC),
                 finished=g <= 3)
        for g in range(1, 8)
    ])
    await db_session.commit()
    db_session.add(LinkedTeam(id=1, fpl_entry_id=77, manager_name="Sam"))

    pid = 1
    squad_ids = []
    for pos, n in _SHAPE:
        for _ in range(n):
            db_session.add(Player(id=pid, team_id=1 + pid % 6, first_name="a", second_name="b",
                                  web_name=f"P{pid}", position=pos, now_cost=50, status="a",
                                  selected_by_percent=1.0, total_points=0))
            squad_ids.append((pid, pos))
            pid += 1
    # a strong replacement MID on the market (not in the squad)
    db_session.add(Player(id=99, team_id=7, first_name="x", second_name="y", web_name="Star",
                          position="MID", now_cost=50, status="a", selected_by_percent=5.0,
                          total_points=0))
    await db_session.commit()

    for i, (p, _pos) in enumerate(squad_ids):
        db_session.add(EntryPick(linked_team_id=1, gameweek_id=3, player_id=p, slot=i + 1,
                                 multiplier=1, is_captain=i == 0, is_vice=i == 1))
    db_session.add(EntryGwHistory(linked_team_id=1, gameweek_id=3, bank=5, team_value=1000))
    db_session.add(Fixture(id=401, gameweek_id=4, home_team_id=1, away_team_id=2,
                           home_difficulty=3, away_difficulty=3, finished=False))
    for p, _pos in squad_ids:
        for h in (1, 2):
            xp = 2.0 if p == 8 else 5.0  # player 8 (a MID) is weak
            db_session.add(PlayerGwPrediction(player_id=p, gameweek_id=3 + h, horizon_gw=h,
                                              model_version="adv-v1", xp=xp,
                                              xp_floor=xp - 1, xp_ceiling=xp + 1))
    for h in (1, 2):
        db_session.add(PlayerGwPrediction(player_id=99, gameweek_id=3 + h, horizon_gw=h,
                                          model_version="adv-v1", xp=9.0,
                                          xp_floor=7.0, xp_ceiling=11.0))
    await db_session.commit()


async def test_optimize_returns_xi_transfers_and_chips(client, db_session):
    await _seed(db_session)
    r = await client.get("/entries/77/optimize?horizon=2&max_transfers=1")
    assert r.status_code == 200
    body = r.json()
    assert body["horizon"] == 2 and body["model"] == "adv-v1"
    assert len(body["current"]["xi"]) == 11
    assert body["current"]["captain"] is not None
    assert isinstance(body["chips"], list)
    # the clear upgrade: swap the weak MID (id 8) for the strong market MID (id 99)
    top = body["transfer_plans"][0]
    assert top["transfers"][0]["out"]["player_id"] == 8
    assert top["transfers"][0]["in"]["player_id"] == 99
    assert top["net"] > 0


async def test_optimize_404_for_unlinked_entry(client, db_session):
    await _seed(db_session)
    assert (await client.get("/entries/999/optimize")).status_code == 404
