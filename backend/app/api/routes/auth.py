"""Эндпоинты входа: состояние, первичная настройка, вход, выход, пароль.

Единственный роутер, который не закрыт зависимостью require_user — иначе
войти было бы нельзя, не войдя. Поэтому каждый метод здесь защищает себя
сам: первичная настройка работает ровно один раз, вход считает неудачные
попытки, смена пароля требует текущего, сброс — аварийного ключа.
"""
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.config import get_settings
from app.core.security import new_random_username
from app.services.auth_service import (
    SESSION_COOKIE,
    authenticate,
    change_password,
    change_username,
    create_admin,
    end_session,
    get_admin,
    is_setup_complete,
    reset_password_with_recovery_key,
    resolve_session,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class SetupRequest(BaseModel):
    username: str = Field(default="admin", min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class ChangeUsernameRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_username: str = Field(min_length=1, max_length=100)


class SuggestedUsername(BaseModel):
    username: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class ResetPasswordRequest(BaseModel):
    recovery_key: str = Field(min_length=1, max_length=500)
    new_password: str = Field(min_length=8, max_length=200)


class AuthState(BaseModel):
    """Что фронтенд спрашивает первым делом, чтобы решить, какой экран
    показать: настройку, форму входа или само приложение."""

    setup_complete: bool
    authenticated: bool
    username: str | None = None
    recovery_available: bool


def _set_session_cookie(response: Response, token: str) -> None:
    """Кука сессии: HttpOnly, чтобы её не достал скрипт на странице, и
    SameSite=Lax, чтобы запрос со стороннего сайта не пришёл от имени
    пользователя. Secure включается настройкой — по умолчанию выключен,
    иначе вход сломался бы на http://localhost, с которого все начинают."""
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
        path="/",
    )


@router.get("/state", response_model=AuthState)
async def read_auth_state(request: Request, session: AsyncSession = Depends(get_session)) -> AuthState:
    user = await resolve_session(session, request.cookies.get(SESSION_COOKIE))
    return AuthState(
        setup_complete=await is_setup_complete(session),
        authenticated=user is not None,
        username=user.username if user is not None else None,
        recovery_available=bool(get_settings().recovery_key),
    )


@router.post("/setup", response_model=AuthState, status_code=201)
async def setup(
    payload: SetupRequest, response: Response, request: Request, session: AsyncSession = Depends(get_session)
) -> AuthState:
    """Первичная настройка: задаёт пароль и сразу впускает.

    Открыта без входа по необходимости и закрывается сама — второй вызов
    отвечает 409 (см. auth_service.create_admin)."""
    user = await create_admin(session, payload.username, payload.password)
    token = await authenticate(
        session,
        payload.username,
        payload.password,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    _set_session_cookie(response, token)
    return AuthState(setup_complete=True, authenticated=True, username=user.username, recovery_available=bool(get_settings().recovery_key))


@router.post("/login", response_model=AuthState)
async def login(
    payload: LoginRequest, response: Response, request: Request, session: AsyncSession = Depends(get_session)
) -> AuthState:
    token = await authenticate(
        session,
        payload.username,
        payload.password,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    _set_session_cookie(response, token)
    user = await get_admin(session)
    return AuthState(
        setup_complete=True,
        authenticated=True,
        username=user.username if user else None,
        recovery_available=bool(get_settings().recovery_key),
    )


@router.get("/suggest-username", response_model=SuggestedUsername)
async def suggest_username() -> SuggestedUsername:
    """Случайный логин для экрана первичной настройки.

    Ничего не сохраняет: человек волен взять предложенный или набрать свой.
    """
    return SuggestedUsername(username=new_random_username())


@router.post("/username", status_code=204)
async def change_own_username(
    payload: ChangeUsernameRequest, session: AsyncSession = Depends(get_session)
) -> None:
    """Смена логина по текущему паролю. Сессии не обрываются: логин меняют
    ради неочевидности, а не из-за утечки."""
    await change_username(session, payload.current_password, payload.new_username)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, session: AsyncSession = Depends(get_session)) -> None:
    await end_session(session, request.cookies.get(SESSION_COOKIE))
    # Куку стираем в любом случае, даже если записи сессии уже не было:
    # браузер не должен остаться с мусорным токеном на две недели.
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post("/password", status_code=204)
async def change_own_password(
    payload: ChangePasswordRequest, request: Request, response: Response, session: AsyncSession = Depends(get_session)
) -> None:
    """Смена пароля по текущему. Завершает все сессии, включая эту — после
    смены пароля нужно войти заново, и это правильно: если пароль меняли
    из-за подозрения на утечку, чужая вкладка не должна её пережить."""
    await change_password(session, payload.current_password, payload.new_password)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post("/recover", status_code=204)
async def reset_password(
    payload: ResetPasswordRequest, response: Response, session: AsyncSession = Depends(get_session)
) -> None:
    """Сброс забытого пароля аварийным ключом из .env."""
    await reset_password_with_recovery_key(session, payload.recovery_key, payload.new_password)
    response.delete_cookie(SESSION_COOKIE, path="/")
