from datetime import UTC, datetime

from fplguru_core.models import Gameweek, Player, PlayerGwPrediction, PlayerGwStat, Team


async def _seed(db_session):
    db_session.add(Team(id=1, name="A", short_name="A"))
    db_session.add_all([
        Gameweek(id=g, name=f"GW{g}", deadline_time=datetime(2025, 8, g, tzinfo=UTC),
                 finished=True)
        for g in (1, 2, 3)
    ])
    await db_session.commit()
    for pid, position in ((11, "MID"), (12, "DEF"), (13, "FWD")):
        db_session.add(Player(id=pid, team_id=1, first_name="a", second_name="b",
                              web_name=f"P{pid}", position=position, now_cost=50, status="a",
                              selected_by_percent=1.0, total_points=0))
    await db_session.commit()
    for gw in (1, 2, 3):
        for pid in (11, 12, 13):
            db_session.add(PlayerGwStat(player_id=pid, gameweek_id=gw, minutes=90,
                                        total_points=5, goals=0, assists=0, clean_sheets=0,
                                        goals_conceded=0, bonus=0, was_home=True,
                                        opponent_team_id=1, value=50))
            db_session.add(PlayerGwPrediction(player_id=pid, gameweek_id=gw, horizon_gw=1,
                                              model_version="basic-v1", xp=4.0,
                                              xp_floor=2.0, xp_ceiling=6.0))
            db_session.add(PlayerGwPrediction(player_id=pid, gameweek_id=gw, horizon_gw=1,
                                              model_version="adv-v1", xp=6.5,
                                              xp_floor=4.0, xp_ceiling=9.0))
    await db_session.commit()


async def test_transparency_reports_metrics_per_model_and_last_gw(client, db_session):
    await _seed(db_session)
    body = (await client.get("/model/transparency?last=2")).json()
    assert body["models"] == ["basic-v1", "adv-v1"]
    assert body["gameweeks"] == [1, 2, 3]

    basic_all = body["by_position"]["basic-v1"]["ALL"]
    assert basic_all["n"] == 9 and abs(basic_all["mae"] - 1.0) < 1e-9  # |4 - 5|
    assert abs(basic_all["bias"] + 1.0) < 1e-9                          # 4 - 5

    adv_all = body["by_position"]["adv-v1"]["ALL"]
    assert abs(adv_all["mae"] - 1.5) < 1e-9                             # |6.5 - 5|

    # rolling window = last 2 GWs -> 6 pairs per model
    assert body["rolling"]["basic-v1"]["ALL"]["n"] == 6

    assert body["last_gw"]["gameweek_id"] == 3
    deltas = [abs(r["delta"]) for r in body["last_gw"]["rows"]]
    assert deltas == sorted(deltas, reverse=True)
    assert {r["model"] for r in body["last_gw"]["rows"]} == {"basic-v1", "adv-v1"}


async def test_transparency_empty_db_is_safe(client, db_session):
    body = (await client.get("/model/transparency")).json()
    assert body["models"] == ["basic-v1", "adv-v1"]
    assert body["by_position"] == {"basic-v1": {}, "adv-v1": {}}
    assert body["last_gw"] is None
