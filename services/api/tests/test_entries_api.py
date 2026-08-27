import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from fplguru_core.models import (
    EntryGwHistory,
    EntryPick,
    Gameweek,
    LinkedTeam,
    Player,
    PlayerGwPrediction,
    Team,
)

BASE = "https://fpl.test/api"
FIX = Path(__file__).parents[3] / "packages/ingest/tests/fixtures"


async def _seed_linked(db_session):
    db_session.add(Team(id=3, name="C", short_name="C"))
    db_session.add_all([
        Gameweek(id=1, name="GW1", deadline_time=datetime(2025, 8, 1, tzinfo=UTC), finished=True),
        Gameweek(id=2, name="GW2", deadline_time=datetime(2025, 8, 8, tzinfo=UTC), is_next=True),
    ])
    await db_session.commit()
    db_session.add(Player(id=12, team_id=3, first_name="c", second_name="d", web_name="Cap",
                          position="MID", now_cost=80, status="a", selected_by_percent=1.0,
                          total_points=0))
    await db_session.commit()
    lt = LinkedTeam(fpl_entry_id=7, manager_name="Sam Q", started_event=1)
    db_session.add(lt)
    await db_session.commit()
    db_session.add(EntryGwHistory(linked_team_id=lt.id, gameweek_id=1, points=55, total_points=55,
                                  overall_rank=1000, bank=5, team_value=1000, transfers=0,
                                  transfer_cost=0, points_on_bench=8))
    db_session.add(EntryPick(linked_team_id=lt.id, gameweek_id=1, player_id=12, slot=12,
                             multiplier=2, is_captain=True, is_vice=False))
    db_session.add(PlayerGwPrediction(player_id=12, gameweek_id=2, horizon_gw=1,
                                      model_version="basic-v1", xp=5.5, xp_floor=3, xp_ceiling=8))
    await db_session.commit()
    return lt.id


@respx.mock
async def test_link_creates_and_returns_entry(client, db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    db_session.add(Team(id=3, name="C", short_name="C"))
    db_session.add_all([
        Gameweek(id=1, name="GW1", deadline_time=datetime(2025, 8, 1, tzinfo=UTC), finished=True),
        Gameweek(id=2, name="GW2", deadline_time=datetime(2025, 8, 8, tzinfo=UTC), is_next=True),
    ])
    await db_session.commit()
    db_session.add_all([
        Player(id=11, team_id=3, first_name="a", second_name="b", web_name="ab", position="GK",
               now_cost=45, status="a", selected_by_percent=1.0, total_points=0),
        Player(id=12, team_id=3, first_name="c", second_name="d", web_name="cd", position="MID",
               now_cost=80, status="a", selected_by_percent=1.0, total_points=0),
    ])
    await db_session.commit()
    respx.get(f"{BASE}/entry/7/").mock(return_value=httpx.Response(
        200, json=json.loads((FIX / "entry_sample.json").read_text())))
    respx.get(f"{BASE}/entry/7/history/").mock(return_value=httpx.Response(
        200, json=json.loads((FIX / "entry_history_sample.json").read_text())))
    respx.get(f"{BASE}/entry/7/event/1/picks/").mock(return_value=httpx.Response(
        200, json=json.loads((FIX / "entry_picks_sample.json").read_text())))

    r = await client.post("/link/7")
    assert r.status_code == 200
    body = r.json()
    assert body["fpl_entry_id"] == 7 and body["manager_name"] == "Sam Q"


async def test_get_entry_squad_with_xp(client, db_session):
    await _seed_linked(db_session)
    r = await client.get("/entries/7")
    body = r.json()
    assert body["manager_name"] == "Sam Q"
    assert body["picks_gameweek_id"] == 1
    cap = next(p for p in body["picks"] if p["is_captain"])
    assert cap["web_name"] == "Cap" and abs(cap["xp"] - 5.5) < 1e-6


async def test_get_entry_history(client, db_session):
    await _seed_linked(db_session)
    r = await client.get("/entries/7/history")
    rows = r.json()
    assert rows[0]["gameweek_id"] == 1 and rows[0]["total_points"] == 55


async def test_get_unknown_entry_404(client):
    assert (await client.get("/entries/999")).status_code == 404
    assert (await client.get("/entries/999/history")).status_code == 404
