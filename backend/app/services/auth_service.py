"""Вход, сессии, смена и сброс пароля.

Заменяет HTTP Basic Auth на nginx, который был в оригинальном Aurum:
браузерное окно без сессии, без выхода и с паролем, летящим в каждом
запросе. Здесь — настоящая сессия, серверная, с возможностью её оборвать.

Три правила, определяющие поведение:

  * **сессия хранится на сервере.** Токен в куке — просто случайная строка,
    всё остальное лежит в таблице sessions. Чисто подписанный токен
    (JWT и подобное) не отзывается: «выйти» ничего не значит, пока он не
    протух сам. Здесь выход удаляет запись, и сессия умирает сразу;
  * **смена пароля требует текущего.** Домохозяйство пользуется одной
    учёткой, и запрет тут не от злоумышленника, а от случайности: жена,
    забредшая в настройки, не должна суметь запереть всех снаружи;
  * **сброс — только аварийным ключом из .env.** Забытый пароль меняется
    строкой, которую знает лишь тот, у кого есть доступ к серверу. Ключ
    намеренно живёт вне базы: открытая чужая вкладка не даёт им
    воспользоваться.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    hash_password,
    needs_rehash,
    new_session_token,
    session_token_fingerprint,
    verify_password,
)
from app.models.user import Session, User

# Имя куки. Префикс __Host- намеренно не используется: он требует Secure и
# ломает вход по http://localhost, с которого начинают все установки.
SESSION_COOKIE = "aurum_session"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_admin(session: AsyncSession) -> User | None:
    """Единственная учётная запись, если она уже заведена."""
    result = await session.execute(select(User).order_by(User.id).limit(1))
    return result.scalar_one_or_none()


async def is_setup_complete(session: AsyncSession) -> bool:
    """Заведён ли пароль. Пока нет — фронтенд показывает экран первичной
    настройки вместо формы входа."""
    return await get_admin(session) is not None


async def create_admin(session: AsyncSession, username: str, password: str) -> User:
    """Создаёт учётную запись. Работает ровно один раз: вторая попытка —
    ошибка, иначе открытый эндпоинт первичной настройки превратился бы в
    способ завести себе доступ к чужой установке."""
    if await get_admin(session) is not None:
        raise HTTPException(status_code=409, detail="Учётная запись уже создана")
    _validate_password_strength(password)

    user = User(username=username, password_hash=hash_password(password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _validate_password_strength(password: str) -> None:
    """Минимальная планка: восемь символов. Сложнее не требуем — правила
    вроде «цифра и спецсимвол» гонят людей к Password1! и не добавляют
    стойкости, а длинная фраза её добавляет."""
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Пароль должен быть не короче 8 символов")


async def authenticate(
    session: AsyncSession,
    username: str,
    password: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> str:
    """Проверяет пароль и открывает сессию. Возвращает токен для куки.

    Ответ на неверное имя и на неверный пароль одинаковый — сообщение не
    должно подсказывать, какая половина не подошла.
    """
    settings = get_settings()
    user = await get_admin(session)
    if user is None:
        raise HTTPException(status_code=400, detail="Учётная запись ещё не создана")

    if user.locked_until is not None and user.locked_until > _now():
        left = int((user.locked_until - _now()).total_seconds() // 60) + 1
        raise HTTPException(status_code=429, detail=f"Слишком много попыток. Повторите через {left} мин.")

    if user.username != username or not verify_password(password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= settings.max_failed_logins:
            user.locked_until = _now() + timedelta(minutes=settings.lockout_minutes)
            user.failed_attempts = 0
        await session.commit()
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    # Вход — единственный момент, когда приложение держит пароль открытым,
    # поэтому ужесточённые параметры хеширования применяются именно здесь.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = _now()

    token = new_session_token()
    session.add(
        Session(
            id=session_token_fingerprint(token),
            user_id=user.id,
            created_at=_now(),
            expires_at=_now() + timedelta(hours=settings.session_ttl_hours),
            user_agent=(user_agent or "")[:255] or None,
            ip_address=(ip_address or "")[:45] or None,
        )
    )
    await session.commit()
    return token


async def resolve_session(session: AsyncSession, token: str | None) -> User | None:
    """Пользователь по токену из куки, либо None.

    Просроченная сессия удаляется здесь же: отдельная уборка по расписанию
    ради одной установки на одного человека — лишняя деталь, а протухшие
    записи всё равно попадаются только при обращении к ним."""
    if not token:
        return None

    row = await session.get(Session, session_token_fingerprint(token))
    if row is None:
        return None
    if row.expires_at <= _now():
        await session.delete(row)
        await session.commit()
        return None

    user = await session.get(User, row.user_id)
    return user if user is not None and user.is_active else None


async def end_session(session: AsyncSession, token: str | None) -> None:
    """Выход: запись сессии удаляется, токен из куки становится бесполезен."""
    if not token:
        return
    row = await session.get(Session, session_token_fingerprint(token))
    if row is not None:
        await session.delete(row)
        await session.commit()


async def change_password(session: AsyncSession, current_password: str, new_password: str) -> None:
    """Смена пароля по текущему. Все прочие сессии завершаются: если пароль
    меняют из-за подозрения, что его узнали, чужая открытая вкладка не
    должна пережить смену."""
    user = await get_admin(session)
    if user is None or not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Текущий пароль неверен")
    _validate_password_strength(new_password)

    user.password_hash = hash_password(new_password)
    await session.execute(delete(Session).where(Session.user_id == user.id))
    await session.commit()


async def reset_password_with_recovery_key(session: AsyncSession, recovery_key: str, new_password: str) -> None:
    """Сброс забытого пароля аварийным ключом из .env.

    Ключ сравнивается с постоянным временем — иначе по времени ответа его
    можно подбирать посимвольно. Незаданный ключ означает, что сброс
    выключен: пустая строка не должна случайно совпасть с пустым вводом.
    """
    from hmac import compare_digest

    settings = get_settings()
    if not settings.recovery_key:
        raise HTTPException(status_code=400, detail="Аварийный сброс не настроен (AURUM_RECOVERY_KEY пуст)")
    if not compare_digest(recovery_key, settings.recovery_key):
        raise HTTPException(status_code=401, detail="Аварийный ключ неверен")

    user = await get_admin(session)
    if user is None:
        raise HTTPException(status_code=400, detail="Учётная запись ещё не создана")
    _validate_password_strength(new_password)

    user.password_hash = hash_password(new_password)
    user.failed_attempts = 0
    user.locked_until = None
    await session.execute(delete(Session).where(Session.user_id == user.id))
    await session.commit()


async def seed_admin_from_env(session: AsyncSession) -> None:
    """Создаёт учётную запись из .env при старте, если она задана и её ещё
    нет. Пароль пуст — приложение просто остаётся в режиме первичной
    настройки, и пароль задаётся в браузере."""
    settings = get_settings()
    if not settings.admin_password:
        return
    if await get_admin(session) is not None:
        return
    if len(settings.admin_password) < 8:
        return
    session.add(
        User(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
        )
    )
    await session.commit()
