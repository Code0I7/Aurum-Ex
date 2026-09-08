from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import SESSION_COOKIE, is_setup_complete, resolve_session

DbSession = AsyncSession


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session


async def require_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    """Пропускает дальше только с живой сессией.

    Вешается на весь /api скопом (см. main.py), а не на каждый роутер по
    отдельности: забытая зависимость на одном эндпоинте — это открытый
    доступ ко всем финансам, и такую ошибку не видно, пока её не найдут.

    Пока пароль не задан, приложение отвечает 428 вместо 401 — фронтенду
    нужно различать "войдите" и "задайте пароль", иначе первичная настройка
    окажется заперта снаружи ещё до того, как её начали.
    """
    user = await resolve_session(session, request.cookies.get(SESSION_COOKIE))
    if user is not None:
        return user

    if not await is_setup_complete(session):
        raise HTTPException(status_code=428, detail="Требуется первичная настройка: задайте пароль")

    raise HTTPException(status_code=401, detail="Требуется вход")
