from datetime import UTC, datetime

from fplguru_core.models import DataSyncLog, Gameweek


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_gameweeks_and_current(client, db_session):
    db_session.add_all([
        Gameweek(id=1, name="Gameweek 1",
                 deadline_time=datetime(2025, 8, 15, 17, 30, tzinfo=UTC), finished=True),
        Gameweek(id=2, name="Gameweek 2",
                 deadline_time=datetime(2025, 8, 22, 17, 30, tzinfo=UTC), is_current=True),
    ])
    await db_session.commit()

    r = await client.get("/gameweeks")
    assert [g["id"] for g in r.json()] == [1, 2]

    r = await client.get("/gameweeks/current")
    assert r.json()["id"] == 2


async def test_status_reports_last_sync(client, db_session):
    now = datetime(2025, 8, 20, 12, 0, tzinfo=UTC)
    db_session.add(DataSyncLog(source="fpl_bootstrap", status="ok",
                               started_at=now, finished_at=now))
    await db_session.commit()

    r = await client.get("/status")
    body = r.json()
    assert body["sources"]["fpl_bootstrap"]["status"] == "ok"
    assert body["sources"]["fpl_bootstrap"]["as_of"].startswith("2025-08-20T12:00:00")
