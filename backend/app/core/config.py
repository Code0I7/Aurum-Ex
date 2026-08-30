"""Application configuration, sourced from environment variables (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Single source of truth for the running app's version — surfaced in the API
# title and embedded in exported backups so an old file can be told apart
# from a current one.
APP_VERSION = "0.20.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AURUM_", extra="ignore")

    # Postgres connection
    postgres_user: str = "aurum"
    postgres_password: str = "aurum"
    postgres_db: str = "aurum"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # Default currency shown across the UI when an account doesn't override it
    default_currency: str = "USD"

    # Comma-separated list of origins allowed to call the API (frontend dev server, etc.)
    cors_origins: str = "*"

    # CoinGecko Demo API key (free, no card required — https://www.coingecko.com/en/api/pricing)
    # for services/crypto_service.py's price lookups. Empty by default; the
    # Crypto tab's endpoints 400 with a clear message until this is set,
    # rather than silently hitting CoinGecko's much stingier keyless tier.
    coingecko_api_key: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
