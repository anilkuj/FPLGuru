from fplguru_core.models import Alert, Base, LinkedTeam


def test_alert_table_and_dedup_uniqueness():
    assert "alerts" in Base.metadata.tables
    uqs = {
        tuple(sorted(c.name for c in con.columns))
        for con in Alert.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    }
    assert ("dedup_key", "linked_team_id") in uqs


def test_linked_team_has_alert_cap():
    col = LinkedTeam.__table__.c.alert_cap
    assert col.nullable is True


def test_linked_team_has_reminder_offsets_default():
    col = LinkedTeam.__table__.c.reminder_offsets
    assert col.nullable is True
    assert col.default is not None                       # python-side default supplies the presets
