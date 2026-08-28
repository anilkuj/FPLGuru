from sqlalchemy import select

from fplguru_core.models import LinkedTeam, PushSubscription


async def _seed(db_session):
    db_session.add(LinkedTeam(id=1, fpl_entry_id=555, manager_name="Sam"))
    await db_session.commit()


async def test_vapid_public_key_endpoint(client, db_session):
    body = (await client.get("/push/vapid-public-key")).json()
    assert "key" in body                       # empty string by default


async def test_subscribe_then_unsubscribe(client, db_session):
    await _seed(db_session)
    sub = {"endpoint": "https://push.test/xyz",
           "keys": {"p256dh": "BPk...", "auth": "abc"}}
    r = await client.post("/entries/555/push/subscribe", json=sub)
    assert r.status_code == 200 and r.json()["ok"] is True

    rows = (await db_session.execute(select(PushSubscription))).scalars().all()
    assert len(rows) == 1 and rows[0].endpoint == "https://push.test/xyz"

    await client.post("/entries/555/push/subscribe", json=sub)   # idempotent upsert
    rows = (await db_session.execute(select(PushSubscription))).scalars().all()
    assert len(rows) == 1

    r = await client.request("DELETE", "/entries/555/push/subscribe",
                             json={"endpoint": "https://push.test/xyz"})
    assert r.status_code == 200 and r.json()["removed"] == 1
    assert (await db_session.execute(select(PushSubscription))).first() is None


async def test_subscribe_unknown_entry_404(client, db_session):
    r = await client.post("/entries/999/push/subscribe",
                          json={"endpoint": "x", "keys": {"p256dh": "a", "auth": "b"}})
    assert r.status_code == 404
