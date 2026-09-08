"""The single administrator account that guards the app.

Not a multi-tenant system, and deliberately so: everyone in the household
signs in as the same administrator, sees the same data, and tells their
transactions apart by участник (models/participant.py) rather than by login.
That is how the household actually works — a shared budget built on trust —
and modelling it as separate tenants would add per-user data isolation
nobody asked for.

What it replaces is the original's HTTP Basic Auth on nginx: a browser
prompt with no session, no way to log out, and the password travelling on
every single request. Fine for localhost, not fine for anything reachable
from outside.

Password rules that matter here:

  * the hash is stored, never the password itself — and never in .env, where
    the original kept it in plain text;
  * changing it from the UI requires the current password, so a family
    member cannot lock everyone out by wandering into settings;
  * a forgotten password is reset with a long recovery key from .env, known
    only to whoever runs the server. That is why the key lives outside the
    database: an attacker with an open browser tab still cannot use it.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    # scrypt-хеш вместе с солью и параметрами в одной строке — формат
    # описан в core/security.py. Параметры лежат внутри строки, поэтому их
    # можно ужесточить, не ломая уже сохранённые пароли.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Защита от перебора: счётчик неудачных попыток и время, до которого
    # вход заблокирован. Сбрасывается при первом успешном входе.
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Session(Base):
    """One signed-in browser. Stored server-side rather than kept purely in
    a signed cookie so that "выйти" actually ends the session — a stateless
    token stays valid until it expires no matter how many times the user
    clicks log out."""

    __tablename__ = "sessions"

    # SHA-256 от токена, который лежит в куке, а не сам токен: у того, кто
    # прочитал базу, не окажется на руках ключей от активных сессий.
    # 64 символа — ровно длина шестнадцатеричного SHA-256.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Для экрана "активные сессии": откуда и с чего заходили.
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
