from datetime import UTC, datetime, timedelta

from fplguru_core.models import Alert, Gameweek, LinkedTeam


async def _seed(db_session):
    db_session.add(Gameweek(id=9, name="GW9",
                            deadline_time=datetime.now(UTC) + timedelta(days=1),
                            is_current=True))
    db_session.add(LinkedTeam(id=1, fpl_entry_id=555, manager_name="Sam"))
    await db_session.commit()
    db_session.add_all([
        Alert(linked_team_id=1, gameweek_id=9, type="availability", dedup_key="a1",
              player_id=None, priority=90, title="Isak: injured", body="Knee", payload={},
              suppressed=False),
        Alert(linked_team_id=1, gameweek_id=9, type="dgw", dedup_key="a2",
              player_id=None, priority=55, title="DGW", body="x", payload={},
              suppressed=False),
        Alert(linked_team_id=1, gameweek_id=9, type="bgw", dedup_key="a3",
              player_id=None, priority=20, title="BGW", body="y", payload={},
              suppressed=True),
    ])
    await db_session.commit()


async def test_alert_feed_default_hides_suppressed_and_sorts_by_priority(client, db_session):
    await _seed(db_session)
    body = (await client.get("/entries/555/alerts")).json()
    assert [a["title"] for a in body["alerts"]] == ["Isak: injured", "DGW"]
    assert body["unseen"] == 2
    assert body["alerts"][0]["seen"] is False


async def test_alert_feed_include_suppressed(client, db_session):
    await _seed(db_session)
    body = (await client.get("/entries/555/alerts?include_suppressed=true")).json()
    assert len(body["alerts"]) == 3


async def test_mark_seen_all(client, db_session):
    await _seed(db_session)
    r = await client.post("/entries/555/alerts/seen", json={})
    assert r.json()["marked"] == 2
    body = (await client.get("/entries/555/alerts")).json()
    assert body["unseen"] == 0
    assert body["alerts"][0]["seen"] is True


async def test_mark_seen_specific_ids(client, db_session):
    await _seed(db_session)
    first = (await client.get("/entries/555/alerts")).json()["alerts"][0]["id"]
    r = await client.post("/entries/555/alerts/seen", json={"ids": [first]})
    assert r.json()["marked"] == 1


async def test_patch_settings_alert_cap(client, db_session):
    await _seed(db_session)
    r = await client.patch("/entries/555/settings", json={"alert_cap": 5})
    assert r.status_code == 200 and r.json()["alert_cap"] == 5
    r2 = await client.patch("/entries/555/settings", json={"alert_cap": None})
    assert r2.json()["alert_cap"] is None


async def test_alerts_unknown_entry_404(client, db_session):
    assert (await client.get("/entries/999/alerts")).status_code == 404


async def test_get_settings_returns_defaults(client, db_session):
    await _seed(db_session)
    body = (await client.get("/entries/555/settings")).json()
    assert body["alert_cap"] is None
    assert body["reminder_offsets"] == [1440, 120, 60, 30]


async def test_patch_settings_reminder_offsets(client, db_session):
    await _seed(db_session)
    r = await client.patch("/entries/555/settings",
                           json={"reminder_offsets": [180, 45, 45, 0, -3]})
    assert r.json()["reminder_offsets"] == [180, 45]
    assert r.json()["alert_cap"] is None
