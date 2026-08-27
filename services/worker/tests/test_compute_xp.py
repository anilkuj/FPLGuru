from datetime import UTC, datetime

from sqlalchemy import func, select

from fplguru_core.models import Fixture, Gameweek, Player, PlayerGwPrediction, PlayerGwStat, Team
from fplguru_ml.model_basic import BasicXP
from fplguru_worker.xp import compute_and_store_xp


async def _seed(db_session):
    db_session.add_all([Team(id=1, name="A", short_name="A"), Team(id=2, name="B", short_name="B")])
    db_session.add_all([
        Gameweek(id=1, name="GW1", deadline_time=datetime(2025, 8, 1, tzinfo=UTC), finished=True),
        Gameweek(id=2, name="GW2", deadline_time=datetime(2025, 8, 8, tzinfo=UTC), finished=True),
        Gameweek(id=3, name="GW3", deadline_time=datetime(2025, 8, 15, tzinfo=UTC), finished=True),
        Gameweek(id=4, name="GW4", deadline_time=datetime(2025, 8, 22, tzinfo=UTC),
                 is_next=True, finished=False),
    ])
    await db_session.commit()
    db_session.add(Player(id=11, team_id=1, first_name="x", second_name="y", web_name="xy",
                          position="MID", now_cost=100, status="a", selected_by_percent=1.0,
                          total_points=20))
    await db_session.commit()
    db_session.add(Fixture(id=104, gameweek_id=4, home_team_id=1, away_team_id=2,
                           home_difficulty=3, away_difficulty=3, finished=False))
    for gw, pts in ((1, 8), (2, 6), (3, 2)):
        db_session.add(PlayerGwStat(player_id=11, gameweek_id=gw, minutes=90, total_points=pts,
                                    goals=0, assists=0, clean_sheets=0, goals_conceded=0,
                                    bonus=0, was_home=True, opponent_team_id=2, value=100))
    await db_session.commit()


async def test_compute_xp_writes_and_is_idempotent(db_session, monkeypatch, tmp_path):
    await _seed(db_session)
    BasicXP({}, global_mean=3.0).save(tmp_path)   # empty bundle -> every predict = 3.0
    monkeypatch.setenv("FPLGURU_XP_ARTIFACT_DIR", str(tmp_path))

    n1 = await compute_and_store_xp(horizon=1)
    assert n1 == 1

    rows = (await db_session.execute(select(PlayerGwPrediction))).scalars().all()
    assert len(rows) == 1
    r = rows[0]
    assert (r.player_id, r.gameweek_id, r.horizon_gw, r.model_version) == (11, 4, 1, "basic-v1")
    assert abs(r.xp - 3.0) < 1e-9 and r.xp_floor < r.xp < r.xp_ceiling
    assert r.x_goals == 0.0  # component breakdown deferred to Advanced

    await compute_and_store_xp(horizon=1)   # second run
    cnt = (await db_session.execute(
        select(func.count()).select_from(PlayerGwPrediction)
    )).scalar()
    assert cnt == 1   # upsert on (player_id, gameweek_id, model_version)


async def test_compute_xp_skips_player_with_thin_history(db_session, monkeypatch, tmp_path):
    db_session.add_all([Team(id=1, name="A", short_name="A"), Team(id=2, name="B", short_name="B")])
    db_session.add_all([
        Gameweek(id=1, name="GW1", deadline_time=datetime(2025, 8, 1, tzinfo=UTC), finished=True),
        Gameweek(id=4, name="GW4", deadline_time=datetime(2025, 8, 22, tzinfo=UTC),
                 is_next=True, finished=False),
    ])
    await db_session.commit()
    db_session.add(Player(id=11, team_id=1, first_name="x", second_name="y", web_name="xy",
                          position="MID", now_cost=100, status="a", selected_by_percent=1.0,
                          total_points=2))
    await db_session.commit()
    db_session.add(Fixture(id=104, gameweek_id=4, home_team_id=1, away_team_id=2,
                           home_difficulty=3, away_difficulty=3, finished=False))
    db_session.add(PlayerGwStat(player_id=11, gameweek_id=1, minutes=90, total_points=2, goals=0,
                                assists=0, clean_sheets=0, goals_conceded=0, bonus=0,
                                was_home=True, opponent_team_id=2, value=100))
    await db_session.commit()
    BasicXP({}, global_mean=3.0).save(tmp_path)
    monkeypatch.setenv("FPLGURU_XP_ARTIFACT_DIR", str(tmp_path))

    n = await compute_and_store_xp(horizon=1)
    assert n == 0   # only 1 appearance < 3 -> feature_row_from_history returns None
