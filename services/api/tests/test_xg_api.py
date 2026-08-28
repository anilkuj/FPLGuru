from datetime import UTC, datetime

from fplguru_core.models import Fixture, Gameweek, Player, PlayerXg, Team


async def _seed(db_session):
    db_session.add(Team(id=1, name="A", short_name="A"))
    db_session.add_all([
        Gameweek(id=g, name=f"GW{g}", deadline_time=datetime(2025, 9, g, tzinfo=UTC),
                 finished=True)
        for g in (3, 4, 5)
    ])
    await db_session.commit()
    db_session.add_all([
        Player(id=1, team_id=1, first_name="a", second_name="b", web_name="Salah",
               position="MID", now_cost=130, status="a"),
        Player(id=2, team_id=1, first_name="c", second_name="d", web_name="Isak",
               position="FWD", now_cost=100, status="a"),
    ])
    db_session.add_all([
        Fixture(id=fid, gameweek_id=g, home_team_id=1, away_team_id=1, home_difficulty=3,
                away_difficulty=3, finished=True)
        for fid, g in ((30, 3), (40, 4), (50, 5))
    ])
    await db_session.commit()
    db_session.add_all([
        PlayerXg(player_id=1, fixture_id=30, gameweek_id=3, minutes=90, xg=0.4, xag=0.2),
        PlayerXg(player_id=1, fixture_id=40, gameweek_id=4, minutes=90, xg=0.7, xag=0.1),
        PlayerXg(player_id=1, fixture_id=50, gameweek_id=5, minutes=80, xg=0.2, xag=0.5),
        PlayerXg(player_id=2, fixture_id=50, gameweek_id=5, minutes=90, xg=1.1, xag=0.0),
    ])
    await db_session.commit()


async def test_player_xg_series_recent_first(client, db_session):
    await _seed(db_session)
    body = (await client.get("/players/1/xg?last=2")).json()
    assert [r["gameweek_id"] for r in body["per_gw"]] == [5, 4]
    assert round(body["totals"]["xg"], 1) == 0.9        # 0.2 + 0.7
    assert body["web_name"] == "Salah"


async def test_xg_snapshot_ranks_by_xg_plus_xag(client, db_session):
    await _seed(db_session)
    body = (await client.get("/xg-snapshot?last=3")).json()
    # player 1: xg 1.3 + xag 0.8 = 2.1 ; player 2: xg 1.1 + xag 0.0 = 1.1
    assert [r["player_id"] for r in body["players"]] == [1, 2]
    assert body["players"][0]["xg"] == 1.3


async def test_xg_snapshot_position_filter(client, db_session):
    await _seed(db_session)
    body = (await client.get("/xg-snapshot?last=3&position=FWD")).json()
    assert [r["player_id"] for r in body["players"]] == [2]


async def test_player_xg_404_when_no_data(client, db_session):
    await _seed(db_session)
    assert (await client.get("/players/999/xg")).status_code == 404
