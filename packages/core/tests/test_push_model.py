from fplguru_core.models import Alert, Base, PushSubscription


def test_push_subscriptions_registered_endpoint_unique():
    assert "push_subscriptions" in Base.metadata.tables
    uqs = {
        tuple(sorted(c.name for c in con.columns))
        for con in PushSubscription.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    }
    assert ("endpoint",) in uqs


def test_alert_has_pushed_at():
    assert "pushed_at" in {c.name for c in Alert.__table__.columns}
