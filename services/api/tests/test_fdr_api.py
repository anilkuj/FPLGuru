from datetime import UTC, datetime

from fplguru_core.models import Fixture, Gameweek, Team


async def _seed(db_session):
    db_session.add_all([
        Team(id=1, name="Aaa", short_name="AAA", strength_overall_home=5, strength_overall_away=5),
        Team(id=2, name="Bbb", short_name="BBB", strength_overall_home=3, strength_overall_away=3),
        Team(id=3, name="Ccc", short_name="CCC", strength_overall_home=4, strength_overall_away=4),
    ])
    db_session.add_all([
        Gameweek(id=g, name=f"GW{g}", deadline_time=datetime(2025, 8, g, tzinfo=UTC),
                 finished=g < 4, is_next=g == 4)
        for g in range(1, 9)
    ])
    await db_session.commit()
    db_session.add_all([
        Fixture(id=1, gameweek_id=1, home_team_id=3, away_team_id=1, home_difficulty=3,
                away_difficulty=3, finished=True, home_score=0, away_score=4),
        Fixture(id=40, gameweek_id=4, home_team_id=2, away_team_id=3, home_difficulty=3,
                away_difficulty=3, finished=False),
        Fixture(id=41, gameweek_id=5, home_team_id=1, away_team_id=2, home_difficulty=3,
                away_difficulty=3, finished=False),
    ])
    await db_session.commit()


async def test_fdr_defaults_to_next_gw(client, db_session):
    await _seed(db_session)
    r = await client.get("/fdr?horizon=5")
    body = r.json()
    assert body["start_gw"] == 4 and body["horizon"] == 5
    teams = {t["short_name"]: t for t in body["teams"]}
    f = next(x for x in teams["BBB"]["fixtures"] if x["gameweek_id"] == 4)
    assert f["opponent_short"] == "CCC" and f["is_home"] is True
    assert 1.0 <= f["fdr"] <= 5.0 and 1 <= f["band"] <= 5
    avgs = [t["avg_fdr"] for t in body["teams"] if t["avg_fdr"] is not None]
    assert avgs == sorted(avgs)


async def test_fdr_explicit_start_and_horizon(client, db_session):
    await _seed(db_session)
    body = (await client.get("/fdr?start_gw=5&horizon=1")).json()
    assert body["start_gw"] == 5
    aaa = next(t for t in body["teams"] if t["short_name"] == "AAA")
    assert [f["gameweek_id"] for f in aaa["fixtures"]] == [5]


async def test_fdr_horizon_out_of_range_422(client, db_session):
    await _seed(db_session)
    assert (await client.get("/fdr?horizon=0")).status_code == 422
    assert (await client.get("/fdr?horizon=11")).status_code == 422
