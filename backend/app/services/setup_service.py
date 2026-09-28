"""Первый запуск: язык и валюта установки.

Раньше и то и другое решалось за человека. Валюта бралась из
`AURUM_DEFAULT_CURRENCY` в `.env` — файла, который при запуске через Docker
человек открывает один раз и больше не помнит; язык не хранился на сервере
вовсе, поэтому засев говорил по-русски всем. В итоге установка в Молдове
начиналась с рублёвых счетов и килограммов кириллицей, и первое, чем
занимался человек, была правка того, чего он не выбирал.

Выбор делается на том же экране, где задаётся пароль: другого момента, когда
приложение уже работает, а данных ещё нет, попросту не существует. Всё, что
здесь происходит, — приведение уже засеянного к выбору; ничего не создаётся
заново и ничего не удаляется.

Ни один шаг не обязателен: пустой выбор оставляет как есть, а установка с
паролем в `.env` этот экран не видит вовсе и живёт на значениях по умолчанию.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed import rename_default_units
from app.models.account import Account
from app.models.currency import Currency
from app.models.transaction import Transaction
from app.services.settings_service import get_or_create_app_settings

# Имя счёта из засева (см. db/seed.py::seed_default_account). По нему и
# отличается счёт, которого человек ещё не касался.
STARTER_ACCOUNT_NAME = "Main Account"


async def apply_first_run_choice(
    session: AsyncSession, language: str | None = None, currency: str | None = None
) -> None:
    """Применяет выбор языка и валюты, сделанный при первичной настройке."""
    settings = await get_or_create_app_settings(session)

    if language:
        settings.language = language
        # Единицы засеяны до того, как язык стал известен: на пустой базе
        # это происходит при первом же запуске приложения.
        await rename_default_units(session, language)

    if currency:
        settings.currency = currency
        await _ensure_currency(session, currency)
        await _retarget_starter_account(session, currency)

    await session.commit()


async def _ensure_currency(session: AsyncSession, code: str) -> None:
    """Заводит валюту в справочнике, если её там ещё нет.

    Справочник заодно служит списком наблюдения, и своя валюта должна быть в
    нём всегда: к ней приводятся все сводные суммы."""
    existing = await session.execute(select(Currency.code).where(Currency.code == code))
    if existing.first() is None:
        session.add(Currency(code=code, symbol=None, name=None, cbr_nominal=1))


async def _retarget_starter_account(session: AsyncSession, currency: str) -> None:
    """Переводит счёт из засева на выбранную валюту.

    Только его и только пока он пуст: счёт, которого человек уже коснулся, —
    его данные, и молча менять у них валюту нельзя. Проверка идёт по числу
    счетов и операций, а не по одному имени: человек мог переименовать счёт
    до того, как завёл первую операцию."""
    accounts = (await session.execute(select(Account))).scalars().all()
    if len(accounts) != 1:
        return

    account = accounts[0]
    used = await session.execute(
        select(func.count())
        .select_from(Transaction)
        .where((Transaction.account_id == account.id) | (Transaction.transfer_account_id == account.id))
    )
    if used.scalar_one() == 0:
        account.currency = currency
