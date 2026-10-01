"""Проверки входа: защита закрытых эндпоинтов, первичная настройка, сессия,
смена пароля, блокировка при переборе.

Смысл этих тестов в том, чтобы поймать самую дорогую ошибку — открытый
доступ к чужим финансам. Она не выглядит как поломка: приложение при ней
работает идеально, просто пускает кого угодно.
"""
import pytest
from httpx import AsyncClient

from tests.conftest import TEST_PASSWORD

pytestmark = pytest.mark.asyncio


async def test_protected_endpoint_requires_setup_before_a_password_exists(anon_client: AsyncClient):
    """Пока пароль не задан, закрытый эндпоинт отвечает 428, а не 401:
    фронтенду нужно отличать «войдите» от «задайте пароль»."""
    resp = await anon_client.get("/accounts")
    assert resp.status_code == 428


async def test_protected_endpoint_rejects_anonymous_after_setup(anon_client: AsyncClient):
    await anon_client.post("/auth/setup", json={"username": "admin", "password": TEST_PASSWORD})
    anon_client.cookies.clear()

    resp = await anon_client.get("/accounts")
    assert resp.status_code == 401


async def test_setup_signs_in_immediately(anon_client: AsyncClient):
    resp = await anon_client.post("/auth/setup", json={"username": "admin", "password": TEST_PASSWORD})
    assert resp.status_code == 201
    assert resp.json() == {
        "setup_complete": True,
        "authenticated": True,
        "username": "admin",
        "recovery_available": False,
    }
    # Кука выдана — следующий запрос проходит без отдельного входа.
    assert (await anon_client.get("/accounts")).status_code == 200


async def test_setup_runs_only_once(anon_client: AsyncClient):
    """Иначе открытый эндпоинт первичной настройки стал бы способом завести
    себе доступ к чужой установке."""
    await anon_client.post("/auth/setup", json={"username": "admin", "password": TEST_PASSWORD})

    resp = await anon_client.post("/auth/setup", json={"username": "intruder", "password": "another-password"})
    assert resp.status_code == 409


async def test_setup_rejects_a_short_password(anon_client: AsyncClient):
    resp = await anon_client.post("/auth/setup", json={"username": "admin", "password": "korotko"})
    assert resp.status_code == 422


async def test_login_with_the_wrong_password_is_rejected(anon_client: AsyncClient):
    await anon_client.post("/auth/setup", json={"username": "admin", "password": TEST_PASSWORD})
    anon_client.cookies.clear()

    resp = await anon_client.post("/auth/login", json={"username": "admin", "password": "не тот пароль"})
    assert resp.status_code == 401
    assert (await anon_client.get("/accounts")).status_code == 401


async def test_login_restores_access(anon_client: AsyncClient):
    await anon_client.post("/auth/setup", json={"username": "admin", "password": TEST_PASSWORD})
    anon_client.cookies.clear()
    assert (await anon_client.get("/accounts")).status_code == 401

    resp = await anon_client.post("/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert resp.status_code == 200
    assert (await anon_client.get("/accounts")).status_code == 200


async def test_logout_ends_the_session_server_side(client: AsyncClient):
    """Главное отличие от подписанного токена: выход должен обрывать сессию
    на сервере, а не только стирать куку в браузере."""
    stolen = dict(client.cookies)

    assert (await client.post("/auth/logout")).status_code == 204
    assert (await client.get("/accounts")).status_code == 401

    # Даже если тот же токен подставить обратно, он уже мёртв.
    for name, value in stolen.items():
        client.cookies.set(name, value)
    assert (await client.get("/accounts")).status_code == 401


async def test_password_change_requires_the_current_one(client: AsyncClient):
    resp = await client.post(
        "/auth/password", json={"current_password": "не тот", "new_password": "new-password-456"}
    )
    assert resp.status_code == 401


async def test_password_change_ends_every_session(client: AsyncClient):
    resp = await client.post(
        "/auth/password", json={"current_password": TEST_PASSWORD, "new_password": "new-password-456"}
    )
    assert resp.status_code == 204
    # После смены пароля прежняя сессия недействительна.
    assert (await client.get("/accounts")).status_code == 401

    # Старый пароль больше не подходит, новый — подходит.
    assert (await client.post("/auth/login", json={"username": "admin", "password": TEST_PASSWORD})).status_code == 401
    assert (
        await client.post("/auth/login", json={"username": "admin", "password": "new-password-456"})
    ).status_code == 200


async def test_repeated_wrong_passwords_lock_the_account(anon_client: AsyncClient):
    """Порог — max_failed_logins из настроек (по умолчанию 10). После
    блокировки даже верный пароль получает 429, иначе перебор просто
    продолжился бы."""
    await anon_client.post("/auth/setup", json={"username": "admin", "password": TEST_PASSWORD})
    anon_client.cookies.clear()

    for _ in range(10):
        assert (
            await anon_client.post("/auth/login", json={"username": "admin", "password": "мимо"})
        ).status_code == 401

    resp = await anon_client.post("/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert resp.status_code == 429


async def test_auth_state_reports_setup_and_session(anon_client: AsyncClient):
    before = (await anon_client.get("/auth/state")).json()
    assert before["setup_complete"] is False
    assert before["authenticated"] is False

    await anon_client.post("/auth/setup", json={"username": "admin", "password": TEST_PASSWORD})

    after = (await anon_client.get("/auth/state")).json()
    assert after["setup_complete"] is True
    assert after["authenticated"] is True
    assert after["username"] == "admin"


async def test_health_stays_open(anon_client: AsyncClient):
    """Healthcheck докера и внешний мониторинг ходят без входа — иначе
    контейнер сам себя объявит нездоровым."""
    resp = await anon_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_recovery_is_unavailable_without_a_key(anon_client: AsyncClient):
    """AURUM_RECOVERY_KEY не задан — сброс выключен целиком, и пустая строка
    в запросе не должна совпасть с пустым ключом в настройках."""
    await anon_client.post("/auth/setup", json={"username": "admin", "password": TEST_PASSWORD})

    resp = await anon_client.post("/auth/recover", json={"recovery_key": "", "new_password": "new-password-456"})
    assert resp.status_code == 422

    resp = await anon_client.post(
        "/auth/recover", json={"recovery_key": "что-угодно", "new_password": "new-password-456"}
    )
    assert resp.status_code == 400
