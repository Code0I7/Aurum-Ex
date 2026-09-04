"""Regression coverage for seed_default_app_settings() respecting
AURUM_DEFAULT_CURRENCY. An earlier version of the 9f3a2d7c5e11 migration
hardcoded the singleton app_settings row to currency='USD' at migration
time — since this function only creates the row when it's missing, that
pre-existing row silently defeated a non-USD AURUM_DEFAULT_CURRENCY on a
fresh install. The migration no longer inserts the row at all; this
function is now the sole place it gets created.
"""
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.seed import seed_default_app_settings
from app.models.settings import AppSettings


async def test_seed_creates_the_row_with_the_configured_currency(test_sessionmaker, monkeypatch):
    monkeypatch.setattr(get_settings(), "default_currency", "GBP")

    async with test_sessionmaker() as session:
        await session.execute(delete(AppSettings))
        await session.commit()

        await seed_default_app_settings(session)

        settings_row = await session.get(AppSettings, 1)
        assert settings_row is not None
        assert settings_row.currency == "GBP"


async def test_seed_never_overwrites_an_existing_row(test_sessionmaker, monkeypatch):
    """Self-healing only kicks in when the row is missing — an existing
    row's currency (e.g. one the user changed via Settings after install)
    must never be silently reset just because the app restarted."""
    async with test_sessionmaker() as session:
        existing = await session.get(AppSettings, 1)
        existing.currency = "EUR"
        await session.commit()

    monkeypatch.setattr(get_settings(), "default_currency", "GBP")

    async with test_sessionmaker() as session:
        await seed_default_app_settings(session)

        settings_row = await session.get(AppSettings, 1)
        assert settings_row.currency == "EUR"
