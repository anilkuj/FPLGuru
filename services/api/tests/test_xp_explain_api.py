from datetime import UTC, datetime

import pandas as pd

from fplguru_core.models import (
    Fixture,
    Gameweek,
    LlmCall,
    Player,
    PlayerGwPrediction,
    PlayerGwStat,
    Team,
    XpRationale,
)
from fplguru_ml.features import FEATURE_NAMES_ADV
from fplguru_ml.model_advanced import train_advanced
from sqlalchemy import func, select


def _tiny_adv_model(tmp_path):
    import numpy as np

    rng = np.random.default_rng(0)
    rows = []
    for pos in ("MID", "DEF"):
        x = rng.normal(size=(120, len(FEATURE_NAMES_ADV)))
        y = 3.0 + 2.0 * (x[:, 0] > 0) + rng.normal(scale=0.4, size=120)
        for i in range(120):
            r = {k: float(x[i, j]) for j, k in enumerate(FEATURE_NAMES_ADV)}
            r.update(position=pos, gameweek=1 + i % 10, target=float(y[i]))
            rows.append(r)
    model = train_advanced(pd.DataFrame(rows), min_rows=50, n_estimators=15, seed=0)
    model.save(tmp_path / "adv")
    return str(tmp_path / "adv")


async def _seed(db_session):
    db_session.add_all([Team(id=1, name="A", short_name="ARS"),
                        Team(id=2, name="B", short_name="LUT")])
    db_session.add_all([
        Gameweek(id=g, name=f"GW{g}", deadline_time=datetime(2025, 8, g, tzinfo=UTC),
                 finished=g <= 3)
        for g in (1, 2, 3, 4, 5)
    ])
    await db_session.commit()
    db_session.add(Player(id=11, team_id=1, first_name="x", second_name="y", web_name="Saka",
                          position="MID", now_cost=100, status="a", selected_by_percent=1.0,
                          total_points=30))
    await db_session.commit()
    db_session.add(Fixture(id=104, gameweek_id=4, home_team_id=1, away_team_id=2,
                           home_difficulty=2, away_difficulty=4, finished=False))
    for gw, pts, g, a in ((1, 8, 1, 0), (2, 6, 0, 1), (3, 9, 1, 1)):
        db_session.add(PlayerGwStat(player_id=11, gameweek_id=gw, minutes=90, total_points=pts,
                                    goals=g, assists=a, clean_sheets=0, goals_conceded=1,
                                    bonus=1, was_home=True, opponent_team_id=2, value=100))
    for h in (1, 2):
        db_session.add(PlayerGwPrediction(player_id=11, gameweek_id=3 + h, horizon_gw=h,
                                          model_version="adv-v1", xp=5.0 + h,
                                          xp_floor=3.0 + h, xp_ceiling=8.0 + h))
    await db_session.commit()


async def test_xp_explain_returns_drivers_and_template_text(client, db_session, monkeypatch,
                                                            tmp_path):
    monkeypatch.setenv("FPLGURU_ADV_XP_ARTIFACT_DIR", _tiny_adv_model(tmp_path))
    await _seed(db_session)

    r = await client.get("/players/11/xp/explain?horizon=2")
    assert r.status_code == 200
    body = r.json()
    assert body["player_id"] == 11 and body["model"] == "adv-v1"
    assert abs(body["xp_total"] - 13.0) < 1e-6
    assert body["source"] == "template"  # no Gemini key configured in tests
    assert "Saka" in body["text"]
    assert isinstance(body["drivers"], list) and len(body["drivers"]) <= 3
    for d in body["drivers"]:
        assert d["feature"] in FEATURE_NAMES_ADV
        assert d["direction"] in ("up", "down")
        assert d["phrase"]


async def test_xp_explain_404_for_unknown_player(client, db_session):
    await _seed(db_session)
    assert (await client.get("/players/999/xp/explain")).status_code == 404


async def test_xp_explain_uses_cache_when_present(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("FPLGURU_ADV_XP_ARTIFACT_DIR", _tiny_adv_model(tmp_path))
    await _seed(db_session)
    db_session.add(XpRationale(player_id=11, gameweek_id=4, model_version="adv-v1",
                               text="Cached rationale.", model="gemini-2.0-flash"))
    await db_session.commit()

    body = (await client.get("/players/11/xp/explain?horizon=2")).json()
    assert body["text"] == "Cached rationale."
    assert body["source"] == "llm"
    # no LLM call attempted
    assert (await db_session.execute(
        select(func.count()).select_from(LlmCall)
    )).scalar() == 0
