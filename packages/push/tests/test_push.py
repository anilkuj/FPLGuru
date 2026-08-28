from fplguru_push import notification_payload, pending_push_targets


def _alert(**kw):
    base = dict(id=1, type="availability", title="Isak: injured", body="Knee",
                priority=90, suppressed=False, seen=False, pushed=False)
    base.update(kw)
    return base


def test_notification_payload_shape():
    p = notification_payload(_alert(id=7, title="T", body="B"))
    assert p == {"title": "T", "body": "B", "tag": "fplguru-7", "url": "/alerts"}


def test_targets_pairs_unpushed_visible_alerts_with_every_subscription():
    alerts = [
        _alert(id=1, priority=90),
        _alert(id=2, priority=10, suppressed=True),   # suppressed -> skip
        _alert(id=3, priority=80, seen=True),         # already seen -> skip
        _alert(id=4, priority=70, pushed=True),       # already pushed -> skip
        _alert(id=5, priority=40),
    ]
    subs = [{"endpoint": "https://a"}, {"endpoint": "https://b"}]
    got = pending_push_targets(alerts, subs, min_priority=50)
    assert sorted((t["subscription"]["endpoint"], t["alert"]["id"]) for t in got) == [
        ("https://a", 1), ("https://b", 1),
    ]  # only alert 1 clears min_priority (5 is 40 < 50)


def test_targets_empty_without_subscriptions():
    assert pending_push_targets([_alert()], [], min_priority=0) == []
