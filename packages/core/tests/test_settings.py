from fplguru_core.settings import Settings


def test_defaults_point_at_local_infra():
    s = Settings(_env_file=None)
    assert s.database_url.startswith("postgresql+asyncpg://")
    assert s.redis_url.startswith("redis://")
    assert s.fpl_api_base == "https://fantasy.premierleague.com/api"


def test_env_prefix_override(monkeypatch):
    monkeypatch.setenv("FPLGURU_ENVIRONMENT", "ci")
    assert Settings(_env_file=None).environment == "ci"
