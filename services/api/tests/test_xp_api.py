from datetime import UTC, datetime

from fplguru_core.models import Gameweek, Player, PlayerGwPrediction, Team


async def _seed(db_session):
    db_session.add(Team(id=1, name="A", short_name="A"))
    db_session.add_all([
        Gameweek(id=4, name="GW4", deadline_time=datetime(2025, 8, 22, tzinfo=UTC), is_next=True),
        Gameweek(id=5, name="GW5", deadline_time=datetime(2025, 8, 29, tzinfo=UTC)),
    ])
    await db_session.commit()
    db_session.add(Player(id=11, team_id=1, first_name="x", second_name="y", web_name="Saka",
                          position="MID", now_cost=100, status="a", selected_by_percent=1.0,
                          total_points=0))
    await db_session.commit()
    for gw, h, xp in ((4, 1, 5.5), (5, 2, 4.0)):
        db_session.add(PlayerGwPrediction(player_id=11, gameweek_id=gw, horizon_gw=h,
                                          model_version="basic-v1", xp=xp,
                                          xp_floor=xp - 2, xp_ceiling=xp + 2))
    await db_session.commit()


async def test_player_xp_breakdown(client, db_session):
    await _seed(db_session)
    r = await client.get("/players/11/xp?horizon=5")
    body = r.json()
    assert body["player_id"] == 11 and body["web_name"] == "Saka"
    assert [g["horizon_gw"] for g in body["per_gw"]] == [1, 2]
    assert abs(body["xp_total"] - 9.5) < 1e-6


async def test_xp_list_sorted_desc(client, db_session):
    await _seed(db_session)
    db_session.add(Player(id=12, team_id=1, first_name="a", second_name="b", web_name="Low",
                          position="DEF", now_cost=40, status="a", selected_by_percent=1.0,
                          total_points=0))
    await db_session.commit()
    db_session.add(PlayerGwPrediction(player_id=12, gameweek_id=4, horizon_gw=1,
                                      model_version="basic-v1", xp=1.0, xp_floor=0, xp_ceiling=2))
    await db_session.commit()
    r = await client.get("/xp?horizon=5")
    rows = r.json()
    assert [x["player_id"] for x in rows] == [11, 12]
    assert rows[0]["xp_total"] == 9.5


async def test_player_xp_404_when_no_predictions(client, db_session):
    await _seed(db_session)
    r = await client.get("/players/999/xp")
    assert r.status_code == 404


async def test_xp_horizon_filter(client, db_session):
    await _seed(db_session)
    r = await client.get("/players/11/xp?horizon=1")
    assert [g["horizon_gw"] for g in r.json()["per_gw"]] == [1]
