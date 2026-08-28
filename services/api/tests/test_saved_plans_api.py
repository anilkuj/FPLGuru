from datetime import UTC, datetime

from sqlalchemy import select

from fplguru_core.models import (
    EntryGwHistory,
    EntryPick,
    Fixture,
    Gameweek,
    LinkedTeam,
    OptimizationPlan,
    Player,
    PlayerGwPrediction,
    Team,
)
from fplguru_core.settings import get_settings

_SHAPE = [("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)]


async def _seed(db_session):
    db_session.add_all([Team(id=t, name=f"T{t}", short_name=f"T{t}") for t in range(1, 8)])
    db_session.add_all([
        Gameweek(id=g, name=f"GW{g}", deadline_time=datetime(2025, 8, g, tzinfo=UTC),
                 finished=g <= 3)
        for g in range(1, 8)
    ])
    await db_session.commit()
    db_session.add_all([
        LinkedTeam(id=1, fpl_entry_id=77, manager_name="Me"),
        LinkedTeam(id=2, fpl_entry_id=88, manager_name="Other"),
    ])
    pid = 1
    ids = []
    for pos, n in _SHAPE:
        for _ in range(n):
            db_session.add(Player(id=pid, team_id=1 + pid % 6, first_name="a", second_name="b",
                                  web_name=f"P{pid}", position=pos, now_cost=50, status="a",
                                  selected_by_percent=1.0, total_points=0))
            ids.append(pid)
            pid += 1
    await db_session.commit()
    for i, p in enumerate(ids):
        db_session.add(EntryPick(linked_team_id=1, gameweek_id=3, player_id=p, slot=i + 1,
                                 multiplier=1, is_captain=i == 0, is_vice=i == 1))
    db_session.add(EntryGwHistory(linked_team_id=1, gameweek_id=3, bank=5, team_value=1000))
    db_session.add(Fixture(id=401, gameweek_id=4, home_team_id=1, away_team_id=2,
                           home_difficulty=3, away_difficulty=3, finished=False))
    for p in ids:
        for h in (1, 2):
            db_session.add(PlayerGwPrediction(player_id=p, gameweek_id=3 + h, horizon_gw=h,
                                              model_version="adv-v1", xp=4.0,
                                              xp_floor=3.0, xp_ceiling=5.0))
    await db_session.commit()


async def test_plan_lifecycle_create_list_get_delete(client, db_session):
    await _seed(db_session)

    created = (await client.post("/entries/77/plans",
                                 json={"name": "pre-DGW", "horizon": 2, "max_transfers": 1})).json()
    assert created["name"] == "pre-DGW" and created["horizon"] == 2
    assert created["model"] == "adv-v1"
    assert len(created["plan"]["current"]["xi"]) == 11
    pid = created["id"]

    lst = (await client.get("/entries/77/plans")).json()
    assert [p["id"] for p in lst] == [pid]
    assert "plan" not in lst[0]

    full = (await client.get(f"/entries/77/plans/{pid}")).json()
    assert full["plan"]["current"]["formation"].count("-") == 2

    r = await client.delete(f"/entries/77/plans/{pid}")
    assert r.status_code == 204
    assert (await client.get("/entries/77/plans")).json() == []


async def test_plan_cap_evicts_oldest(client, db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "saved_plans_cap", 3)
    await _seed(db_session)
    for i in range(5):
        await client.post("/entries/77/plans", json={"name": f"p{i}", "horizon": 1})
    lst = (await client.get("/entries/77/plans")).json()
    assert len(lst) == 3
    assert [p["name"] for p in lst] == ["p4", "p3", "p2"]  # newest first, oldest evicted


async def test_plan_scoped_to_linked_team(client, db_session):
    await _seed(db_session)
    db_session.add(OptimizationPlan(linked_team_id=2, name="theirs", horizon=1,
                                    max_transfers=0, model_version="adv-v1", payload="{}"))
    await db_session.commit()
    other_id = (await db_session.execute(select(OptimizationPlan.id))).scalar()
    assert (await client.get(f"/entries/77/plans/{other_id}")).status_code == 404


async def test_plans_404_for_unlinked_entry(client, db_session):
    await _seed(db_session)
    assert (await client.get("/entries/999/plans")).status_code == 404
