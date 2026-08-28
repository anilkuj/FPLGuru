from datetime import UTC, datetime

from fplguru_core.models import (
    EntryPick,
    Gameweek,
    LinkedTeam,
    Player,
    PlayerGwPrediction,
    Team,
)

_SHAPE = [("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)]


async def _seed(db_session):
    db_session.add_all([Team(id=t, name=f"T{t}", short_name=f"T{t}") for t in range(1, 7)])
    db_session.add_all([
        Gameweek(id=g, name=f"GW{g}", deadline_time=datetime(2025, 8, g, tzinfo=UTC),
                 finished=g <= 3)
        for g in range(1, 7)
    ])
    await db_session.commit()
    db_session.add_all([
        LinkedTeam(id=1, fpl_entry_id=77, manager_name="Me"),
        LinkedTeam(id=2, fpl_entry_id=88, manager_name="Rival"),
    ])

    ids = []
    pid = 1
    for pos, n in _SHAPE:
        for _ in range(n):
            db_session.add(Player(id=pid, team_id=1 + pid % 5, first_name="a", second_name="b",
                                  web_name=f"P{pid}", position=pos, now_cost=50, status="a",
                                  selected_by_percent=1.0, total_points=0))
            ids.append((pid, pos))
            pid += 1
    # two extra players only the rival owns
    db_session.add(Player(id=201, team_id=6, first_name="r", second_name="a", web_name="RivDef",
                          position="DEF", now_cost=55, status="a", selected_by_percent=2.0,
                          total_points=0))
    db_session.add(Player(id=202, team_id=6, first_name="r", second_name="b", web_name="RivMid",
                          position="MID", now_cost=60, status="a", selected_by_percent=2.0,
                          total_points=0))
    await db_session.commit()

    for i, (p, _pos) in enumerate(ids):
        db_session.add(EntryPick(linked_team_id=1, gameweek_id=3, player_id=p, slot=i + 1,
                                 multiplier=1, is_captain=i == 0, is_vice=i == 1))
    # rival: same 15 but swap one DEF (id 3) -> 201 and one MID (id 8) -> 202
    rival_ids = [(201 if p == 3 else 202 if p == 8 else p) for p, _ in ids]
    for i, p in enumerate(rival_ids):
        db_session.add(EntryPick(linked_team_id=2, gameweek_id=3, player_id=p, slot=i + 1,
                                 multiplier=1, is_captain=i == 0, is_vice=i == 1))

    for p, _pos in ids + [(201, "DEF"), (202, "MID")]:
        for h in (1, 2):
            xp = 9.0 if p in (201, 202) else 4.0
            db_session.add(PlayerGwPrediction(player_id=p, gameweek_id=3 + h, horizon_gw=h,
                                              model_version="adv-v1", xp=xp,
                                              xp_floor=xp - 1, xp_ceiling=xp + 1))
    await db_session.commit()


async def test_h2h_compares_two_squads(client, db_session, monkeypatch):
    async def _stub(eid):
        return 2

    monkeypatch.setattr("fplguru_api.main.sync_entry", _stub)
    await _seed(db_session)

    r = await client.get("/entries/77/h2h/88?horizon=2")
    assert r.status_code == 200
    body = r.json()
    assert body["opponent_entry_id"] == 88 and body["opponent_name"] == "Rival"
    assert body["model"] == "adv-v1"
    assert "your_xi_total" in body and "their_xi_total" in body
    assert round(body["margin"], 2) == round(
        body["your_xi_total"] - body["their_xi_total"], 2
    )
    assert {p["player_id"] for p in body["their_differentials"]} == {201, 202}
    assert {p["player_id"] for p in body["your_differentials"]} == {3, 8}
    assert body["strategy"]


async def test_h2h_404_when_my_entry_unlinked(client, db_session, monkeypatch):
    monkeypatch.setattr("fplguru_api.main.sync_entry", lambda eid: None)
    await _seed(db_session)
    assert (await client.get("/entries/999/h2h/88")).status_code == 404


async def test_h2h_404_when_opponent_has_no_squad(client, db_session, monkeypatch):
    async def _stub(eid):
        return 3

    monkeypatch.setattr("fplguru_api.main.sync_entry", _stub)
    await _seed(db_session)
    db_session.add(LinkedTeam(id=3, fpl_entry_id=99, manager_name="Empty"))
    await db_session.commit()
    assert (await client.get("/entries/77/h2h/99")).status_code == 404
