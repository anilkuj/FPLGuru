import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx
from sqlalchemy import func, select

from fplguru_core.models import EntryGwHistory, EntryPick, Gameweek, LinkedTeam, Player, Team
from fplguru_worker.entries import sync_entry

FIX = Path(__file__).parents[3] / "packages/ingest/tests/fixtures"
ENTRY = json.loads((FIX / "entry_sample.json").read_text())
HIST = json.loads((FIX / "entry_history_sample.json").read_text())
PICKS = json.loads((FIX / "entry_picks_sample.json").read_text())
BASE = "https://fpl.test/api"


async def _seed(db_session):
    db_session.add(Team(id=3, name="C", short_name="C"))
    db_session.add_all([
        Gameweek(id=1, name="GW1", deadline_time=datetime(2025, 8, 1, tzinfo=UTC), finished=True),
        Gameweek(id=2, name="GW2", deadline_time=datetime(2025, 8, 8, tzinfo=UTC), finished=True),
    ])
    await db_session.commit()
    db_session.add_all([
        Player(id=11, team_id=3, first_name="a", second_name="b", web_name="ab", position="GK",
               now_cost=45, status="a", selected_by_percent=1.0, total_points=0),
        Player(id=12, team_id=3, first_name="c", second_name="d", web_name="cd", position="MID",
               now_cost=80, status="a", selected_by_percent=1.0, total_points=0),
    ])
    await db_session.commit()


@respx.mock
async def test_sync_entry_creates_link_history_and_picks(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    await _seed(db_session)
    respx.get(f"{BASE}/entry/7/").mock(return_value=httpx.Response(200, json=ENTRY))
    respx.get(f"{BASE}/entry/7/history/").mock(return_value=httpx.Response(200, json=HIST))
    respx.get(f"{BASE}/entry/7/event/2/picks/").mock(return_value=httpx.Response(200, json=PICKS))

    lt_id = await sync_entry(7)

    lt = (await db_session.execute(select(LinkedTeam).where(LinkedTeam.id == lt_id))).scalar_one()
    assert lt.fpl_entry_id == 7 and lt.manager_name == "Sam Q"
    hist = (await db_session.execute(
        select(EntryGwHistory).where(EntryGwHistory.linked_team_id == lt_id)
    )).scalars().all()
    assert {h.gameweek_id for h in hist} == {1, 2}
    picks = (await db_session.execute(
        select(EntryPick).where(EntryPick.linked_team_id == lt_id)
    )).scalars().all()
    assert {p.player_id for p in picks} == {11, 12} and any(p.is_captain for p in picks)


@respx.mock
async def test_sync_entry_is_idempotent(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    await _seed(db_session)
    respx.get(f"{BASE}/entry/7/").mock(return_value=httpx.Response(200, json=ENTRY))
    respx.get(f"{BASE}/entry/7/history/").mock(return_value=httpx.Response(200, json=HIST))
    respx.get(f"{BASE}/entry/7/event/2/picks/").mock(return_value=httpx.Response(200, json=PICKS))

    a = await sync_entry(7)
    b = await sync_entry(7)
    assert a == b
    n = (await db_session.execute(
        select(func.count()).select_from(EntryPick).where(EntryPick.linked_team_id == a)
    )).scalar()
    assert n == 2


@respx.mock
async def test_sync_entry_tolerates_picks_404(db_session, monkeypatch):
    monkeypatch.setenv("FPLGURU_FPL_API_BASE", BASE)
    await _seed(db_session)
    respx.get(f"{BASE}/entry/7/").mock(return_value=httpx.Response(200, json=ENTRY))
    respx.get(f"{BASE}/entry/7/history/").mock(return_value=httpx.Response(200, json=HIST))
    respx.get(f"{BASE}/entry/7/event/2/picks/").mock(return_value=httpx.Response(404))

    lt_id = await sync_entry(7)   # must not raise
    picks = (await db_session.execute(
        select(func.count()).select_from(EntryPick).where(EntryPick.linked_team_id == lt_id)
    )).scalar()
    assert picks == 0
