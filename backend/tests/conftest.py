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
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Кука сессии без флага Secure — до любого импорта приложения, потому что
# настройки читаются один раз при импорте и кешируются.
#
# На опубликованном экземпляре в .env стоит AURUM_SECURE_COOKIES=true, и это
# правильно. Но тестовый клиент ходит по http://test: браузерное правило
# «Secure только по HTTPS» соблюдает и httpx, кука до запроса не доезжает, и
# падает весь набор разом — на ровном месте, из-за настройки, к которой ни
# один тест отношения не имеет. Команда из tests/README.md обязана работать
# на любом экземпляре, а не только на локальном.
os.environ["AURUM_SECURE_COOKIES"] = "false"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_session
from app.core.config import get_settings
from app.core.security import (
    hash_password,
    new_session_token,
    session_token_fingerprint,
)
from app.db.base import Base
from app.db.seed import (
    seed_default_account,
    seed_default_app_settings,
    seed_default_categories,
    seed_default_currencies,
    seed_default_units,
)
from app.main import app
from app.models.user import Session as UserSession, User
from app.services.auth_service import SESSION_COOKIE

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


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_sessionmaker(_test_database) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Один движок на весь прогон.

    Был свой на каждый тест, и причина была настоящая: pytest-asyncio
    давал каждому тесту отдельный цикл событий, а соединение asyncpg
    принадлежит тому циклу, в котором открыто, — пул из чужого цикла
    выдавал «attached to a different loop». Расплатой было пересоздание
    движка и холодное соединение на каждый тест.

    Теперь цикл один на прогон (см. pytest.ini), и оговорка перестала
    действовать. pool_pre_ping остаётся: соединение, которое Postgres
    закрыл со своей стороны за долгий прогон, должно замениться, а не
    уронить тест.
    """
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


# Пароль тестовой установки.
TEST_PASSWORD = "test-password-123"


@pytest.fixture(scope="session")
def test_password_hash() -> str:
    """Хеш тестового пароля — один на весь прогон.

    scrypt дорог намеренно: 16 МБ памяти и около 79 мс на хеш, чтобы
    перебор пароля не окупался. Для живого входа это ровно то, что нужно, а
    для подготовки каждого из шестисот тестов — две минуты прогона на одно
    и то же вычисление с одним и тем же ответом.

    Сам scrypt при этом проверяется: параметры и формат строки — в
    tests/platform/test_auth.py, через настоящие эндпоинты входа и смены
    пароля."""
    return hash_password(TEST_PASSWORD)


@pytest_asyncio.fixture
async def session(test_sessionmaker) -> AsyncGenerator[AsyncSession, None]:
    """Прямой доступ к базе — для записей, которых нет в API.

    Курс валюты на дату заводится именно так: загрузка ходит на сайт ЦБ, а
    тесты не должны зависеть от того, жив ли он.
    """
    async with test_sessionmaker() as db:
        yield db

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
async def client(
    anon_client: AsyncClient, test_sessionmaker, test_password_hash: str
) -> AsyncClient:
    """Клиент с открытой сессией — то, чем пользуется подавляющее
    большинство тестов.

    Раньше фикстура проходила настоящую первичную настройку через HTTP.
    Путь честный, но дорогой: внутри scrypt, и 220 мс уходило на каждый из
    шестисот тестов, которые проверяют не вход, а деньги.

    Поэтому учётная запись и сессия заводятся прямо в базе, с заранее
    посчитанным хешем. Состояние получается то же, что после настройки:
    есть пользователь — значит установка завершена, есть запись сессии —
    значит клиент вошёл. Что настоящая настройка и настоящий вход работают,
    проверяют tests/platform/test_auth.py и test_first_run_setup.py: они
    берут `anon_client` и ходят по эндпоинтам.
    """
    token = new_session_token()
    now = datetime.now(timezone.utc)
    async with test_sessionmaker() as db:
        user = User(username="admin", password_hash=test_password_hash)
        db.add(user)
        await db.flush()
        db.add(
            UserSession(
                id=session_token_fingerprint(token),
                user_id=user.id,
                created_at=now,
                expires_at=now + timedelta(hours=get_settings().session_ttl_hours),
            )
        )
        await db.commit()
    # Кука ставится руками, как её поставил бы ответ эндпоинта входа: httpx
    # дальше носит её сам, и запросы идут как из браузера.
    anon_client.cookies.set(SESSION_COOKIE, token)
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
