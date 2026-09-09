"""Test harness wiring.

Everything here talks to a dedicated ``aurum_test`` Postgres database on the
same server the app already uses — created fresh, migrated with the real
Alembic chain, and dropped again at the end of the run. The app's own
``AsyncSessionLocal``/``lifespan`` (which would touch the real ``aurum``
database with the user's actual financial history) is never invoked: the
ASGI app is exercised directly over httpx without running startup events,
and the ``get_session`` dependency is overridden per-test to point at the
test database instead. See tests/README.md for how to run this.
"""
import asyncio
import os
import subprocess
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_session
from app.core.config import get_settings
from app.db.base import Base
from app.db.seed import (
    seed_default_account,
    seed_default_app_settings,
    seed_default_categories,
    seed_default_currencies,
    seed_default_units,
)
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_NAME = "aurum_test"

_base_settings = get_settings()


def _url(db_name: str) -> str:
    return (
        f"postgresql+asyncpg://{_base_settings.postgres_user}:{_base_settings.postgres_password}"
        f"@{_base_settings.postgres_host}:{_base_settings.postgres_port}/{db_name}"
    )


async def _drop_and_create_test_database() -> None:
    engine = create_async_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    await engine.dispose()


async def _drop_test_database() -> None:
    engine = create_async_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
    await engine.dispose()


@pytest.fixture(scope="session")
def _test_database() -> Generator[None, None, None]:
    """Create aurum_test from scratch and run every Alembic migration
    against it. Connects to Postgres' always-present `postgres` maintenance
    database to issue CREATE/DROP DATABASE — the real `aurum` database is
    never opened by this fixture.

    Deliberately a *sync* fixture that drives asyncio.run() itself rather
    than an async one: session-scoped async fixtures need to share a loop
    with function-scoped async tests, which pytest-asyncio doesn't do by
    default and led to "attached to a different loop" errors here. A plain
    sync fixture sidesteps the whole question — asyncio.run() opens and
    cleanly closes its own throwaway loop for each of the two calls below.
    """
    asyncio.run(_drop_and_create_test_database())

    env = {**os.environ, "AURUM_POSTGRES_DB": TEST_DB_NAME}
    subprocess.run(["alembic", "upgrade", "head"], cwd=BACKEND_DIR, env=env, check=True)

    yield

    asyncio.run(_drop_test_database())


@pytest_asyncio.fixture
async def test_sessionmaker(_test_database) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    # Function-scoped, not session-scoped: pytest-asyncio gives each test
    # function its own event loop, and an asyncpg engine/pool created under
    # one loop can't be reused from another ("attached to a different
    # loop"). Recreating the engine per test keeps it bound to whichever
    # loop is actually running.
    engine = create_async_engine(_url(TEST_DB_NAME), pool_pre_ping=True)
    yield async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


# Очистка между тестами: DELETE в порядке зависимостей плюс сброс всех
# счётчиков одним запросом.
#
# Раньше здесь было 35 отдельных TRUNCATE ... RESTART IDENTITY CASCADE — по
# одному на таблицу. На пустых таблицах это стоило 830 мс на тест: TRUNCATE
# берёт исключительную блокировку, переписывает файл и правит системный
# каталог, и делает это 35 раз подряд. Весь набор из-за одного этого шёл
# семь минут.
#
# DELETE на таблице в десяток строк дешевле в разы: 71 мс на ту же работу
# вместе с засевом. Порядок — обратный порядку зависимостей (тот же, что был
# у TRUNCATE), поэтому CASCADE не нужен: дети удаляются раньше родителей.
#
# Счётчики сбрасываются отдельным запросом по всем последовательностям
# схемы, а не по списку таблиц: RESTART IDENTITY делал ровно это, а тесты
# полагаются на предсказуемые идентификаторы.
_RESET_SEQUENCES = text(
    "SELECT setval(c.oid::regclass, 1, false) FROM pg_class c "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE c.relkind = 'S' AND n.nspname = 'public'"
)


@pytest_asyncio.fixture(autouse=True)
async def _clean_database(test_sessionmaker):
    """Wipe every table and reseed the default categories/account/app
    settings before each test, so tests never see leftovers from a previous
    one and never have to guess at auto-incremented IDs from prior runs."""
    async with test_sessionmaker() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(text(f'DELETE FROM "{table.name}"'))
        await session.execute(_RESET_SEQUENCES)
        await session.commit()
        await seed_default_categories(session)
        # Валюты и единицы засеваются и здесь: без них установка неполная,
        # а тест, который этого не заметит, проверяет не то приложение,
        # которое получает пользователь.
        await seed_default_currencies(session)
        await seed_default_units(session)
        await seed_default_account(session)
        await seed_default_app_settings(session)
    yield


# Пароль тестовой установки. Задаётся через первичную настройку, как это
# делает живой пользователь, а не подсовыванием готового хеша в базу — так
# тесты заодно проверяют, что настройка и вход действительно работают.
TEST_PASSWORD = "test-password-123"


@pytest_asyncio.fixture
async def anon_client(test_sessionmaker) -> AsyncGenerator[AsyncClient, None]:
    """Клиент без входа — для проверок самой защиты: что закрытый эндпоинт
    отвечает 401, что первичная настройка отрабатывает один раз, что перебор
    пароля упирается в блокировку."""
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(anon_client: AsyncClient) -> AsyncClient:
    """Клиент с открытой сессией — то, чем пользуется подавляющее
    большинство тестов. Проходит первичную настройку и остаётся с кукой
    сессии: httpx хранит её сам, поэтому дальше запросы идут как из
    браузера вошедшего пользователя."""
    resp = await anon_client.post("/auth/setup", json={"username": "admin", "password": TEST_PASSWORD})
    assert resp.status_code == 201, resp.text
    return anon_client


@pytest_asyncio.fixture
async def account_id(client: AsyncClient) -> int:
    """The default seeded account (see app/db/seed.py) — every transaction
    needs one, and the app itself always seeds exactly this one on first
    boot, so tests build on the same shape real usage does."""
    resp = await client.get("/accounts")
    accounts = resp.json()
    assert accounts, "seed_default_account should have created exactly one account"
    return accounts[0]["id"]


@pytest_asyncio.fixture
async def categories(client: AsyncClient) -> dict[str, dict]:
    """Default seeded categories keyed by name, e.g. categories["Groceries"]["id"]."""
    resp = await client.get("/categories")
    return {c["name"]: c for c in resp.json()}
