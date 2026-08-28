from celery import Celery

from fplguru_core.settings import get_settings

settings = get_settings()

celery_app = Celery("fplguru", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    timezone="UTC",
    task_track_started=True,
    task_acks_late=True,
    beat_schedule={
        "sync-bootstrap": {"task": "sync_bootstrap", "schedule": 900.0},   # every 15 min
        "sync-fixtures": {"task": "sync_fixtures", "schedule": 3600.0},    # hourly
        "sync-gw-stats": {"task": "sync_gw_stats", "schedule": 3600.0},    # hourly
        "compute-xp": {"task": "compute_xp", "schedule": 3600.0},          # hourly
        "sync-linked-teams": {"task": "sync_linked_teams", "schedule": 3600.0},
        "poll-live": {"task": "poll_live", "schedule": settings.live_poll_seconds},
        "generate-alerts": {"task": "generate_alerts", "schedule": 1800.0},
        "deliver-push": {"task": "deliver_push", "schedule": 60.0},
        "sync-league-standings": {"task": "sync_league_standings", "schedule": 7200.0},
    },
)

from fplguru_worker import tasks  # noqa: E402,F401  (register tasks)
