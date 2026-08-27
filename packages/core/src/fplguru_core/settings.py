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


@lru_cache
def get_settings() -> Settings:
    return Settings()
