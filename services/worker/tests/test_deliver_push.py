from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from fplguru_core.models import Alert, Gameweek, LinkedTeam, PushSubscription
from fplguru_worker import tasks


async def _seed(db_session):
    db_session.add(Gameweek(id=9, name="GW9",
                            deadline_time=datetime.now(UTC) + timedelta(days=1),
                            is_current=True))
    db_session.add(LinkedTeam(id=1, fpl_entry_id=555, manager_name="Sam"))
    await db_session.commit()
    db_session.add_all([
        Alert(linked_team_id=1, gameweek_id=9, type="availability", dedup_key="a1",
              priority=90, title="Isak: injured", body="Knee", payload={}, suppressed=False),
        Alert(linked_team_id=1, gameweek_id=9, type="bgw", dedup_key="a2",
              priority=20, title="BGW", body="x", payload={}, suppressed=True),
        PushSubscription(linked_team_id=1, endpoint="https://push.test/aaa",
                         p256dh="k", auth="s"),
    ])
    await db_session.commit()


async def test_deliver_push_sends_unpushed_visible_alerts_and_marks_them(db_session, monkeypatch):
    await _seed(db_session)
    sent = []
    monkeypatch.setattr(tasks, "_send_web_push", lambda sub, payload: sent.append((sub, payload)))
    await tasks._deliver_push()

    assert len(sent) == 1
    assert sent[0][1]["title"] == "Isak: injured"
    a1 = (await db_session.execute(
        select(Alert).where(Alert.dedup_key == "a1")
    )).scalar_one()
    assert a1.pushed_at is not None

    sent.clear()
    await tasks._deliver_push()
    assert sent == []


async def test_deliver_push_noop_without_subscriptions(db_session, monkeypatch):
    db_session.add(LinkedTeam(id=2, fpl_entry_id=999, manager_name="No Subs"))
    await db_session.commit()
    called = []
    monkeypatch.setattr(tasks, "_send_web_push", lambda *a: called.append(a))
    await tasks._deliver_push()
    assert called == []


async def test_deliver_push_prunes_gone_subscriptions(db_session, monkeypatch):
    await _seed(db_session)

    def _boom(sub, payload):
        raise tasks.PushGone("410")

    monkeypatch.setattr(tasks, "_send_web_push", _boom)
    await tasks._deliver_push()
    remaining = (await db_session.execute(select(PushSubscription))).scalars().all()
    assert remaining == []
