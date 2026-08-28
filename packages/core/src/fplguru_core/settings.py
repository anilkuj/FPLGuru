from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="FPLGURU_", extra="ignore"
    )

    database_url: str = "postgresql+asyncpg://fplguru:fplguru@localhost:5432/fplguru"
    redis_url: str = "redis://localhost:6379/0"
    fpl_api_base: str = "https://fantasy.premierleague.com/api"
    environment: str = "local"
    xp_artifact_dir: str = "packages/ml/artifacts/basic"
    adv_xp_artifact_dir: str = "packages/ml/artifacts/advanced"
    live_poll_seconds: float = 60.0          # Beat cadence for poll_live
    live_stream_poll_seconds: float = 5.0    # how often the SSE endpoint re-reads the DB
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@fplguru.local"
    gemini_api_key: str = ""
    gemini_base: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-2.0-flash"
    llm_monthly_usd_cap: float = 5.0
    saved_plans_cap: int = 5
    pitchapi_key: str = ""
    pitchapi_base: str = "https://api.pitchapi.dev/v1"
    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
