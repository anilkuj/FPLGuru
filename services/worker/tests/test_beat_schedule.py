from fplguru_worker.app import celery_app


def test_beat_schedule_registers_all_scheduled_tasks():
    sched = celery_app.conf.beat_schedule
    assert sched["sync-bootstrap"]["task"] == "sync_bootstrap"
    assert sched["sync-fixtures"]["task"] == "sync_fixtures"
    assert sched["sync-gw-stats"]["task"] == "sync_gw_stats"
    assert sched["compute-xp"]["task"] == "compute_xp"
    assert sched["sync-linked-teams"]["task"] == "sync_linked_teams"
    assert sched["poll-live"]["task"] == "poll_live"
    assert sched["sync-bootstrap"]["schedule"] <= 900.0
