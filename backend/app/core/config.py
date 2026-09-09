"""Application configuration, sourced from environment variables (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Single source of truth for the running app's version — surfaced in the API
# title, /api/health (which the frontend reads to show it in Settings), and
# embedded in exported backups so an old file can be told apart from a
# current one.
APP_VERSION = "1.0.0-beta.17"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AURUM_", extra="ignore")

    # Postgres connection
    postgres_user: str = "aurum"
    postgres_password: str = "aurum"
    postgres_db: str = "aurum"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # Default currency shown across the UI when an account doesn't override it
    default_currency: str = "RUB"

    # Comma-separated list of browser origins allowed to call the API. Empty
    # by default, which allows none: the shipped compose serves the UI and the
    # API from one nginx, and the Vite dev server proxies /api, so neither is
    # a cross-origin caller. Set it only for a genuinely separate frontend.
    cors_origins: str = ""

    # CoinGecko Demo API key (free, no card required — https://www.coingecko.com/en/api/pricing)
    # for services/crypto_service.py's price lookups. Empty by default; the
    # Crypto tab's endpoints 400 with a clear message until this is set,
    # rather than silently hitting CoinGecko's much stingier keyless tier.
    coingecko_api_key: str = ""

    # --- Вход (см. services/auth_service.py) ---

    # Имя администратора. Одна учётная запись на всё домохозяйство: люди
    # различаются участником в транзакции, а не логином.
    admin_username: str = "admin"

    # Пароль администратора для первого запуска. Если пуст, приложение
    # поднимается в режиме первичной настройки и просит задать пароль в
    # браузере — так он не остаётся в открытом виде в файле на диске.
    # Задан — учётная запись создаётся при старте; после этого значение
    # можно (и стоит) убрать из .env, пароль уже лежит в базе хешем.
    admin_password: str = ""

    # Аварийный ключ для сброса забытого пароля. Длинная случайная строка,
    # которую знает только владелец сервера: обычная смена пароля требует
    # текущего, а этот ключ — единственный обход. Пуст по умолчанию, и
    # тогда сброс просто недоступен.
    recovery_key: str = ""

    # Сколько живёт сессия без повторного входа. Две недели — компромисс
    # между "не логиниться каждый день" и "чужая вкладка не остаётся
    # открытой навсегда".
    session_ttl_hours: int = 24 * 14

    # Защита от перебора: сколько неудачных попыток подряд до блокировки и
    # на сколько минут блокировать. Считается по учётной записи, а не по
    # адресу — учётка одна, и подобрать её пароль с разных адресов не легче.
    max_failed_logins: int = 10
    lockout_minutes: int = 15

    # Ставить ли на куку сессии флаг Secure (только по HTTPS). По умолчанию
    # выключено, иначе вход сломается на http://localhost, с которого
    # начинают все. Включить при публикации наружу за TLS.
    secure_cookies: bool = False

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
